"""The benchmark runner: executes cases across models and assembles a BenchmarkRun."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path

from model_swap_bench.config.models import BenchmarkCase, BenchmarkSuite, ExecutionMode, ModelCandidate
from model_swap_bench.errors import ProviderError, ProviderTimeoutError, ProviderUnavailableError
from model_swap_bench.evaluators import EvalContext, resolve_evaluator
from model_swap_bench.execution.context import ExecutionContext
from model_swap_bench.execution.retry import RetryOutcome, call_with_retry
from model_swap_bench.execution.scheduler import run_bounded
from model_swap_bench.providers.base import Provider, ProviderResponse, build_provider
from model_swap_bench.results import (
    BenchmarkRun,
    CaseResult,
    CaseStatus,
    EvalStatus,
    ProviderCall,
    TokenUsage,
    utcnow,
)
from model_swap_bench.scoring import aggregation, replacement
from model_swap_bench.storage.manifests import build_manifest, manifest_hash


def new_run_id() -> str:
    return f"run-{utcnow():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def _effective_latency(response: ProviderResponse, measured_ms: float) -> float:
    simulated = response.raw.get("simulated_latency_ms")
    if isinstance(simulated, (int, float)):
        return float(simulated)
    return measured_ms


async def run_case(
    ctx: ExecutionContext,
    model: ModelCandidate,
    provider: Provider,
    case: BenchmarkCase,
) -> CaseResult:
    """Execute one case against one model, evaluate, and score it."""
    request = ctx.build_request(model, case)
    outcome = RetryOutcome()
    started = utcnow()
    t0 = time.perf_counter()
    result = CaseResult(
        run_id=ctx.run_id,
        case_id=case.id,
        model_alias=model.alias,
        status=CaseStatus.ERROR,
        weight=case.weight,
        started_at=started,
    )
    try:
        response = await call_with_retry(
            lambda: provider.complete(request),
            retries=(model.retries if model.retries is not None else ctx.suite.execution.retries),
            outcome=outcome,
        )
    except ProviderTimeoutError as exc:
        result.status = CaseStatus.TIMEOUT
        result.error = str(exc)
        result.retries = outcome.retries
        result.latency_ms = (time.perf_counter() - t0) * 1000.0
        result.finished_at = utcnow()
        return result
    except (ProviderUnavailableError, ProviderError) as exc:
        result.status = CaseStatus.ERROR
        result.error = str(exc)
        result.retries = outcome.retries
        result.finished_at = utcnow()
        return result

    measured_ms = (time.perf_counter() - t0) * 1000.0
    latency_ms = _effective_latency(response, measured_ms)
    from model_swap_bench.scoring import economics

    cost = economics.estimate_call_cost(
        model,
        ctx.suite.scoring,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        latency_ms=latency_ms,
    )
    result.raw_output = response.text if ctx.suite.privacy.store_raw_outputs else None
    result.latency_ms = latency_ms
    result.tokens = TokenUsage(input_tokens=response.input_tokens, output_tokens=response.output_tokens)
    result.estimated_cost_usd = cost
    result.tool_calls = response.tool_calls
    result.retries = outcome.retries
    result.provider_call = ProviderCall(
        provider=model.provider.value,
        requested_model=model.model,
        reported_model=response.reported_model,
        execution_path=response.execution_path,
        endpoint=response.endpoint,
    )

    eval_ctx = EvalContext(
        case=case,
        output_text=response.text,
        latency_ms=latency_ms,
        cost_usd=cost,
        tool_calls=list(response.tool_calls),
    )
    for spec in ctx.suite.effective_evaluators(case):
        evaluator = resolve_evaluator(spec)
        result.evaluations.append(evaluator.evaluate(eval_ctx))
    result.parsed_output = eval_ctx.parsed

    graded = [e for e in result.evaluations if e.status is not EvalStatus.SKIPPED]
    result.status = CaseStatus.SUCCESS if all(e.passed for e in graded) else CaseStatus.FAILED
    result.finished_at = utcnow()
    return result


class BenchmarkRunner:
    """Coordinates a full benchmark run."""

    def __init__(self, suite: BenchmarkSuite, *, suite_dir: Path | None = None, allow_hosted: bool = False) -> None:
        self.suite = suite
        self.suite_dir = suite_dir
        self.allow_hosted = allow_hosted

    def _models(self, only: set[str] | None) -> list[ModelCandidate]:
        if only:
            return [m for m in self.suite.models if m.alias in only]
        return list(self.suite.models)

    def _mode(self, models: Sequence[ModelCandidate]) -> ExecutionMode:
        if self.suite.execution.mode is not None:
            return self.suite.execution.mode
        if self.suite.cascade is not None:
            return ExecutionMode.CASCADE
        if self.suite.replacement is not None:
            return ExecutionMode.BASELINE_VS_CANDIDATE
        return ExecutionMode.SINGLE if len(models) == 1 else ExecutionMode.COMPARISON

    async def run(self, *, run_id: str | None = None, only_models: set[str] | None = None) -> BenchmarkRun:
        run_id = run_id or new_run_id()
        models = self._models(only_models)
        mode = self._mode(models)
        ctx = ExecutionContext(suite=self.suite, run_id=run_id, allow_hosted=self.allow_hosted)
        run = BenchmarkRun(
            run_id=run_id,
            suite_name=self.suite.name,
            suite_version=self.suite.version,
            mode=mode.value,
            baseline_model=self.suite.baseline_model,
        )

        if mode is ExecutionMode.CASCADE and self.suite.cascade is not None:
            from model_swap_bench.execution.cascade import run_cascade

            await run_cascade(self, ctx, run)
        else:
            await self._run_comparison(ctx, run, models)

        self._finalize(run, models)
        run.manifest_hash = manifest_hash(build_manifest(self.suite, run_id, self.suite_dir))
        return run

    async def _run_comparison(self, ctx: ExecutionContext, run: BenchmarkRun, models: Sequence[ModelCandidate]) -> None:
        for model in models:
            provider = build_provider(model, suite_dir=self.suite_dir, allow_hosted=self.allow_hosted)
            try:
                health = await provider.health()
                if not health.available:
                    run.warnings.append(f"model {model.alias!r} provider unavailable: {health.detail}")
                factories: list[Callable[[], Awaitable[CaseResult]]] = []
                for case in self.suite.cases:
                    for _ in range(self.suite.execution.repetitions):
                        factories.append(self._case_factory(ctx, model, provider, case))
                results = await run_bounded(factories, self.suite.execution.concurrency)
            finally:
                await provider.aclose()
            run.case_results.extend(results)

    def _case_factory(
        self, ctx: ExecutionContext, model: ModelCandidate, provider: Provider, case: BenchmarkCase
    ) -> Callable[[], Awaitable[CaseResult]]:
        async def _factory() -> CaseResult:
            return await run_case(ctx, model, provider, case)

        return _factory

    def _finalize(self, run: BenchmarkRun, models: Sequence[ModelCandidate]) -> None:
        by_alias: dict[str, list[CaseResult]] = {m.alias: [] for m in models}
        for result in run.case_results:
            by_alias.setdefault(result.model_alias, []).append(result)
        model_by_alias = {m.alias: m for m in self.suite.models}
        for model in models:
            summary = aggregation.build_model_summary(model, by_alias.get(model.alias, []))
            run.model_summaries.append(summary)
            run.constraint_results[model.alias] = aggregation.check_constraints(summary, self.suite.constraints)

        if self.suite.replacement is not None:
            baseline_summary = run.summary_for(self.suite.replacement.baseline)
            if baseline_summary is not None:
                for cand_alias in self.suite.replacement.candidates:
                    cand_summary = run.summary_for(cand_alias)
                    cand_model = model_by_alias.get(cand_alias)
                    if cand_summary is None or cand_model is None:
                        continue
                    decision = replacement.decide_replacement(
                        baseline_summary,
                        cand_summary,
                        cand_model,
                        self.suite.replacement,
                        candidate_constraints=run.constraint_results.get(cand_alias, []),
                        privacy_allows_hosted=self.suite.privacy.allow_hosted_providers,
                        cascade=run.cascade_summary,
                    )
                    run.replacement_decisions.append(decision)

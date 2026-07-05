# Cost per successful outcome

The primary economic metric:

```
cost_per_success = total_cost / successful_cases
```

If there are **zero** successful cases, cost per success is **undefined** and
reported as `n/a` — never a divide-by-zero. A cheap model that fails often is not
cheaper per *successful outcome*.

## Cost modes

Set `scoring.cost_mode`:

### zero_marginal (default)

```
token_cost = input_tokens/1e6 * input_price + output_tokens/1e6 * output_price
```

Local models with zero prices cost `$0` — useful for pure token/API comparison.

### estimated_compute

Adds a local-compute estimate from `scoring.compute_profile`:

```yaml
scoring:
  cost_mode: estimated_compute
  compute_profile:
    electricity_price_per_kwh: 0.15
    watts: 250
    hardware_amortization_per_hour: 0.05
    cloud_gpu_hourly_rate: 0.0
    fixed_overhead_per_run_usd: 0.0
```

Compute cost per call ≈ `(energy + amortization + cloud-GPU-equivalent) × runtime`.

**All compute figures are estimates and clearly labeled as such.** ModelSwapBench
never presents them as measured billing. Pricing values come from an editable,
versioned registry (see `modelswapbench pricing show`) that always warns about
staleness.

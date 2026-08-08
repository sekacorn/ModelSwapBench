# Sanitized trace replay

Replay JSONL can carry request/response messages, tools/results, retrieval
summaries, requested and actual models, provider, tokens, latency, errors,
timeouts, human outcome, risk, and privacy classification.

```bash
modelswapbench replay sanitize traces.jsonl \
  --output traces.sanitized.jsonl \
  --preflight-output replay-preflight.json \
  --provider-mode local
```

Sanitization masks common identifiers and credentials, hashes correlation IDs,
and can omit content or retain bounded excerpts. It cannot guarantee removal of
domain-specific sensitive data; inspect outputs before hosted use.

# Adding a provider

Providers are provider-neutral by contract. To add one:

1. Subclass `model_swap_bench.providers.base.Provider`:

```python
from model_swap_bench.config.models import ProviderKind
from model_swap_bench.providers.base import HealthStatus, Provider, ProviderRequest, ProviderResponse

class MyProvider(Provider):
    kind = ProviderKind.OPENAI_COMPATIBLE  # or a new kind you add to the enum

    async def health(self) -> HealthStatus:
        # No side effects; report availability of endpoint + model.
        ...

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        # Map request -> your API -> ProviderResponse. Record execution_path + endpoint.
        ...

    async def aclose(self) -> None:
        ...
```

2. If it's a genuinely new backend, add a value to `ProviderKind` and wire it in
   `providers.base.build_provider`.

3. Respect the rules:
   - No silent hosted fallback; classify local vs external endpoints.
   - Read API keys from `candidate.api_key_env`; never store or log them.
   - Raise the structured errors in `model_swap_bench.errors` (`ProviderUnavailableError`,
     `ProviderTimeoutError`, `ProviderResponseError`).
   - Record `execution_path` honestly.

4. Add offline tests (mock the transport or test pure logic like classification).

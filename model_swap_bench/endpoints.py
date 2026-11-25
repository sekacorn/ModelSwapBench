"""Classifying an endpoint as local or external.

This lives in its own module because two layers need the same answer and
neither should import the other: the configuration layer decides whether a
candidate is hosted, and the provider layer decides whether to refuse a run.
A second copy of the rule in either place would be a rule that can disagree
with itself.

What "local" means here is deliberately narrow: loopback, the unspecified
address, or a private network. Everything else is external, including a
hostname that happens to resolve to a private address, because a name is not a
route and this check never performs DNS.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from collections.abc import Iterable
from typing import Final
from urllib.parse import urlparse, urlsplit

#: 0.0.0.0 is accepted because development servers bind it to mean "this host".
LOCAL_HOSTNAMES: Final = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})  # nosec B104


#: Documentation (RFC 5737, RFC 3849), benchmarking (RFC 2544), reserved
#: (RFC 1112, 240.0.0.0/4) and limited broadcast (255.255.255.255) addresses.
#: Python's ``is_private`` includes them, but they are neither this machine nor
#: a private network, so an endpoint there is hosted. The same ranges are
#: excluded in AgentForge, ModelSwapBench and the AI Infrastructure Suite, and
#: the shared ``endpoint-locality-cases.v1`` table pins all three.
NOT_LOCAL_NETWORKS: Final = tuple(
    ipaddress.ip_network(network)
    for network in (
        "192.0.2.0/24",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "198.18.0.0/15",
        "240.0.0.0/4",
        "255.255.255.255/32",
        "2001:db8::/32",
    )
)


def _in_not_local_network(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Whether ``address``, or the IPv4 address it maps, is in a range above."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return any(address in network for network in NOT_LOCAL_NETWORKS)


def endpoint_is_local(base_url: str) -> bool:
    """Whether ``base_url`` points at this machine or a private network.

    Returns ``False`` for anything it cannot positively establish as local,
    including a malformed URL or an empty host. An endpoint this function
    cannot classify is treated as external, because the cost of being wrong in
    that direction is a refused run rather than content leaving the machine
    unannounced.
    """
    try:
        host = urlparse(base_url).hostname or ""
    except ValueError:
        # A URL that cannot be parsed (an unclosed IPv6 bracket, say) is not
        # positively local, so it is hosted. AgentForge and the AI
        # Infrastructure Suite answer the same way.
        return False
    if host in LOCAL_HOSTNAMES:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # A hostname. Not resolved on purpose: resolution is a network call,
        # and a name that resolves privately today may not tomorrow.
        return False
    if _in_not_local_network(address):
        return False
    return bool(address.is_private or address.is_loopback or address.is_link_local)


#: Raised verbatim. Each says how to fix the problem and never repeats the URL.
URL_CREDENTIALS_MESSAGE: Final = (
    "base_url must not contain credentials (user:password@host). Remove them from the URL and supply the key through api_key_env."
)
URL_FRAGMENT_MESSAGE: Final = "base_url must not contain a fragment (#...)."
URL_QUERY_MESSAGE: Final = (
    "base_url must not contain a query string. Put parameters the endpoint requires in default_query, "
    "whose values are redacted in run artefacts and logs."
)

#: Bounds on ``default_query``: a few named parameters such as ``api-version``.
MAX_DEFAULT_QUERY_PARAMS: Final = 16
MAX_DEFAULT_QUERY_VALUE_CHARS: Final = 512
REDACTED: Final = "[redacted]"
_QUERY_KEY = re.compile(r"[A-Za-z0-9_.-]{1,64}")


def url_has_credentials(base_url: str) -> bool:
    """Whether ``base_url`` carries a username or password.

    Such a URL is refused rather than used. Run artefacts record each model's
    endpoint, and HTTP clients log the request URL, so a password placed in the
    URL would be written to every manifest, result file and log. A URL that
    cannot be parsed is judged by whether its authority contains ``@``.
    """
    try:
        parts = urlsplit(base_url)
        return parts.username is not None or parts.password is not None
    except ValueError:
        authority = base_url.split("//", 1)[-1].split("/", 1)[0]
        return "@" in authority


def url_problem(base_url: str) -> str | None:
    """Why a configured ``base_url`` is refused, as a fixed message, or ``None``.

    Credentials, fragments and query strings are all refused. Run artefacts
    record each model's endpoint and the HTTP client logs every request URL, so
    anything secret in the URL would be written to both. Parameters an endpoint
    needs go in ``default_query`` instead. The message never contains any part
    of the URL.
    """
    if url_has_credentials(base_url):
        return URL_CREDENTIALS_MESSAGE
    if "#" in base_url:
        return URL_FRAGMENT_MESSAGE
    if "?" in base_url:
        return URL_QUERY_MESSAGE
    return None


def default_query_problem(default_query: object) -> str | None:
    """Why a ``default_query`` is refused, as a fixed message, or ``None``."""
    if not isinstance(default_query, dict):
        return "default_query must be a mapping of parameter names to string values."
    if len(default_query) > MAX_DEFAULT_QUERY_PARAMS:
        return "default_query has too many parameters."
    for key, value in default_query.items():
        if not isinstance(key, str) or not _QUERY_KEY.fullmatch(key):
            return "default_query has an invalid parameter name."
        if not isinstance(value, str) or not value or len(value) > MAX_DEFAULT_QUERY_VALUE_CHARS:
            return "default_query has an invalid value."
    return None


# --- keeping default_query values out of logs ---------------------------------

_LOGGERS_THAT_PRINT_URLS: Final = ("httpx", "httpcore")
_QUERY_VALUE = re.compile(r"([?&][^=&\s\"'#]+=)[^&\s\"'#]+")
_SECRET_QUERY_VALUES: set[str] = set()


class _RedactQueryValues(logging.Filter):
    """Replace query-string values, and any registered value, in a log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - never break logging over redaction
            return True
        redacted = _QUERY_VALUE.sub(lambda m: m.group(1) + REDACTED, message)
        for value in sorted(_SECRET_QUERY_VALUES, key=len, reverse=True):
            redacted = redacted.replace(value, REDACTED)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


_FILTER = _RedactQueryValues()


def redact_query_values_in_logs(values: Iterable[str] = ()) -> None:
    """Keep query values, and these values in particular, out of HTTP client logs.

    Idempotent. Installed whenever a provider is given a ``default_query``.
    """
    _SECRET_QUERY_VALUES.update(value for value in values if value)
    for name in _LOGGERS_THAT_PRINT_URLS:
        logger = logging.getLogger(name)
        if _FILTER not in logger.filters:
            logger.addFilter(_FILTER)

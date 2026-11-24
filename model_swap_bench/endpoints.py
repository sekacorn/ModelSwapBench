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
from typing import Final
from urllib.parse import urlparse, urlsplit

#: 0.0.0.0 is accepted because development servers bind it to mean "this host".
LOCAL_HOSTNAMES: Final = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})  # nosec B104


def endpoint_is_local(base_url: str) -> bool:
    """Whether ``base_url`` points at this machine or a private network.

    Returns ``False`` for anything it cannot positively establish as local,
    including a malformed URL or an empty host. An endpoint this function
    cannot classify is treated as external, because the cost of being wrong in
    that direction is a refused run rather than content leaving the machine
    unannounced.
    """
    host = urlparse(base_url).hostname or ""
    if host in LOCAL_HOSTNAMES:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # A hostname. Not resolved on purpose: resolution is a network call,
        # and a name that resolves privately today may not tomorrow.
        return False
    return bool(address.is_private or address.is_loopback or address.is_link_local)


#: Raised verbatim. It says how to fix the problem and never repeats the URL.
URL_CREDENTIALS_MESSAGE: Final = (
    "base_url must not contain credentials (user:password@host). Remove them from the URL and supply the key through api_key_env."
)


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

"""Usage events: counters, timings, status and the serving key. Never prompt or response content.

One ``UsageEvent`` is recorded per inference that reached the gateway (see ``GatewayInference.stream``). The quota port is
only a hook for now: ``prepare`` calls it and the default never denies.
"""
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


def estimate_tokens(characters: int) -> int:
    """The stand-in used when the gateway gave no usage (cancel, failure, old gateway): one token per four characters, rounded up."""
    return -(-characters // 4)


@dataclass(frozen=True)
class UsageEvent:
    event_id: UUID
    organization_id: UUID
    membership_id: UUID
    alias: str
    upstream_id: str
    key_id: UUID | None
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    ttfb_ms: int | None
    status: str  # ok | cancelled | error
    error_code: str | None
    source: str  # gateway | estimated


class UsageRecorder(Protocol):
    def record(self, event: UsageEvent) -> bool: ...


class QuotaPolicy(Protocol):
    def check(self, organization_id: UUID, membership_id: UUID | None) -> None:
        """Raise ``GatewayDenied`` to refuse a request before any outbound call (reserved for a future quota)."""


class AllowAll:
    def check(self, organization_id, membership_id):
        return None

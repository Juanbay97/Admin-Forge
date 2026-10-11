"""Server-owned alias domain, not authentication or live router verification.

Only a future trusted adapter/publisher may supply real verified route evidence.
A VERIFIED enum in a constructed object does not establish that trust. This module
does no IO, accepts no provider credentials or URLs, and publishes no API endpoint.
"""

from dataclasses import dataclass, field
from enum import Enum
import re
from uuid import UUID


class CatalogInvalid(ValueError):
    """The trusted input is incomplete, inconsistent or unsupported."""


class CatalogDenied(ValueError):
    """The requested organization/alias is outside this catalog."""


class Modality(Enum):
    TEXT = "text"
    IMAGE = "image"


class Verification(Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"


def _require(condition: bool) -> None:
    if not condition:
        raise CatalogInvalid("Invalid model catalog")


def _uuid(value: object) -> None:
    _require(type(value) is UUID)


def _positive_integer(value: object) -> None:
    _require(type(value) is int and value > 0)


def _modalities(value: object) -> None:
    _require(type(value) is frozenset and bool(value))
    _require(all(type(item) is Modality for item in value))


@dataclass(frozen=True, slots=True)
class Capabilities:
    """Known capabilities only; missing/unknown values are invalid, not support."""

    input_modalities: frozenset[Modality]
    output_modalities: frozenset[Modality]
    tools: bool
    streaming: bool
    max_context_tokens: int
    max_output_tokens: int

    def __post_init__(self) -> None:
        _modalities(self.input_modalities)
        _modalities(self.output_modalities)
        _require(type(self.tools) is bool and type(self.streaming) is bool)
        _positive_integer(self.max_context_tokens)
        _positive_integer(self.max_output_tokens)
        _require(self.max_output_tokens <= self.max_context_tokens)

    def public_projection(self) -> dict[str, object]:
        return {
            "input_modalities": sorted(item.value for item in self.input_modalities),
            "output_modalities": sorted(item.value for item in self.output_modalities),
            "tools": self.tools,
            "streaming": self.streaming,
            "max_context_tokens": self.max_context_tokens,
            "max_output_tokens": self.max_output_tokens,
        }


@dataclass(frozen=True, slots=True)
class UnknownCapabilities:
    """An ID listing proves no modality, limit, tool or streaming support."""

    def public_projection(self) -> dict[str, object]:
        return {
            "capability_state": "unknown", "verification": "unverified",
            "input_modalities": None, "output_modalities": None,
            "tools": None, "streaming": None,
            "max_context_tokens": None, "max_output_tokens": None,
        }


@dataclass(frozen=True, slots=True)
class RouteEvidence:
    """Private opaque references, not employee routing inputs or stored secrets."""

    organization_id: UUID
    router_binding_id: UUID = field(repr=False)
    route_id: UUID = field(repr=False)
    evidence_id: UUID = field(repr=False)
    verification: Verification
    capabilities: Capabilities | UnknownCapabilities

    def __post_init__(self) -> None:
        for value in (self.organization_id, self.router_binding_id,
                      self.route_id, self.evidence_id):
            _uuid(value)
        _require(type(self.verification) is Verification)
        _require(type(self.capabilities) in (Capabilities, UnknownCapabilities))
        if type(self.capabilities) is UnknownCapabilities:
            _require(self.verification is Verification.UNVERIFIED)


@dataclass(frozen=True, slots=True)
class AliasSnapshot:
    name: str
    routes: tuple[RouteEvidence, ...] = field(repr=False)
    capabilities: Capabilities | UnknownCapabilities = field(init=False)

    def __post_init__(self) -> None:
        _require(type(self.name) is str)
        _require(re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", self.name) is not None)
        _require(type(self.routes) is tuple and bool(self.routes))
        _require(all(type(route) is RouteEvidence for route in self.routes))
        first = self.routes[0]
        _require(len({route.route_id for route in self.routes}) == len(self.routes))
        for route in self.routes:
            _require(route.organization_id == first.organization_id)
            _require(route.router_binding_id == first.router_binding_id)
            _require((route.verification is Verification.VERIFIED and type(route.capabilities) is Capabilities)
                     or (route.verification is Verification.UNVERIFIED and type(route.capabilities) is UnknownCapabilities))

        if type(first.capabilities) is UnknownCapabilities:
            _require(all(type(route.capabilities) is UnknownCapabilities for route in self.routes))
            object.__setattr__(self, "capabilities", UnknownCapabilities())
            return
        _require(all(type(route.capabilities) is Capabilities for route in self.routes))

        # Advertising the union would allow a fallback to violate the contract.
        capabilities = tuple(route.capabilities for route in self.routes)
        inputs = frozenset.intersection(*(item.input_modalities for item in capabilities))
        outputs = frozenset.intersection(*(item.output_modalities for item in capabilities))
        conservative = Capabilities(
            input_modalities=inputs,
            output_modalities=outputs,
            tools=all(item.tools for item in capabilities),
            streaming=all(item.streaming for item in capabilities),
            max_context_tokens=min(item.max_context_tokens for item in capabilities),
            max_output_tokens=min(item.max_output_tokens for item in capabilities),
        )
        object.__setattr__(self, "capabilities", conservative)


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    """Validated input snapshot; publication and membership authority are external."""

    organization_id: UUID
    router_binding_id: UUID = field(repr=False)
    revision: int
    aliases: tuple[AliasSnapshot, ...]

    def __post_init__(self) -> None:
        _uuid(self.organization_id)
        _uuid(self.router_binding_id)
        _positive_integer(self.revision)
        _require(type(self.aliases) is tuple and bool(self.aliases))
        _require(all(type(alias) is AliasSnapshot for alias in self.aliases))
        _require(len({alias.name for alias in self.aliases}) == len(self.aliases))
        for alias in self.aliases:
            for route in alias.routes:
                _require(route.organization_id == self.organization_id)
                _require(route.router_binding_id == self.router_binding_id)

    def select_alias(self, organization_id: UUID, name: str) -> AliasSnapshot:
        """Exact catalog lookup only, never membership authorization."""
        if type(organization_id) is UUID and organization_id == self.organization_id:
            if type(name) is str:
                for alias in self.aliases:
                    if alias.name == name:
                        return alias
        raise CatalogDenied("Model alias unavailable")

    def public_projection(self) -> dict[str, object]:
        """Fresh allowlisted data, deliberately not a deployed JSON API schema."""
        return {
            "organization_id": str(self.organization_id),
            "revision": self.revision,
            "models": [
                {"id": alias.name, **alias.capabilities.public_projection()}
                for alias in self.aliases
            ],
        }


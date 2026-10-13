"""Platform view of usage: versioned model prices (edits are new audited versions) and, from 0037, the cross-company reports.

Authority is the database (a fresh verified platform owner on every call). This service only bounds arguments, turns the
bearer capability into its digest and returns finite, content-free values (counters, integers in micro-USD and identifiers).
"""
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Protocol
from uuid import UUID

from forge.invitations import capability_digest
from forge.platform import PlatformInvalid

UPSTREAM = re.compile(r'[!-~]{1,255}')
MAX_PRICE = 10 ** 9  # micro-USD per million tokens


@dataclass(frozen=True)
class ModelPrice:
    id: int
    upstream_id: str
    version: int
    input_micros: int
    output_micros: int
    currency: str
    effective_from: datetime
    set_by: UUID


class PriceStore(Protocol):
    def set_price(self, digest, upstream_id, input_micros, output_micros, effective_from) -> ModelPrice: ...
    def prices(self, digest, upstream_id) -> list: ...


def _model(value):
    if type(value) is not str or not UPSTREAM.fullmatch(value):
        raise PlatformInvalid()
    return value


def _price(value):
    if type(value) is not int or not 0 <= value <= MAX_PRICE:
        raise PlatformInvalid()
    return value


class PlatformUsage:
    def __init__(self, store):
        self._store = store

    def set_price(self, token, upstream_id, input_micros, output_micros, effective_from=None):
        _model(upstream_id)
        _price(input_micros), _price(output_micros)
        if effective_from is not None and (type(effective_from) is not datetime or effective_from.tzinfo is None):
            raise PlatformInvalid()
        return self._store.set_price(capability_digest(token), upstream_id, input_micros, output_micros, effective_from)

    def prices(self, token, upstream_id=None):
        if upstream_id is not None:
            _model(upstream_id)
        return self._store.prices(capability_digest(token), upstream_id)

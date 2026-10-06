"""Internal commands only: callers authorize the mutation, not this envelope."""
from dataclasses import dataclass
from uuid import UUID


EVENT_TYPES = ('membership.updated', 'department.created')


@dataclass(frozen=True, repr=False)
class Event:
    event_id: UUID
    organization_id: UUID
    actor_id: UUID
    request_id: UUID
    resource_id: UUID
    event_type: str
    previous_revision: int
    revision: int

    def __post_init__(self):
        if (any(type(value) is not UUID for value in (self.event_id, self.organization_id,
                self.actor_id, self.request_id, self.resource_id))
                or self.event_type not in EVENT_TYPES
                or type(self.previous_revision) is not int or type(self.revision) is not int
                or not 0 <= self.previous_revision < 2**63 - 1
                or self.revision != self.previous_revision + 1):
            raise ValueError('Invalid outbox event')

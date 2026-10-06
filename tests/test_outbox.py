"""Immutable, bounded event commands; no arbitrary metadata."""
import unittest
import sys
from pathlib import Path
from uuid import UUID
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


class OutboxTests(unittest.TestCase):
    def test_event_preserves_explicit_stable_identifiers(self):
        from forge.outbox import Event
        event = Event(*(UUID(int=n) for n in range(1, 6)),
                      'membership.updated', 1, 2)
        self.assertEqual(event.event_id, UUID(int=1))
        self.assertEqual((event.previous_revision, event.revision), (1, 2))
        self.assertNotIn(str(UUID(int=2)), repr(event))

    def test_invalid_event_fields_are_rejected_without_echo(self):
        from forge.outbox import Event
        values = [*(UUID(int=n) for n in range(1, 6)), 'membership.updated', 1, 2]
        for index, invalid in ((0, 'secret-marker'), (1, None), (5, 'secret-marker'),
                               (6, -1), (6, True), (7, 1), (7, 2**63)):
            with self.subTest(index=index, value=invalid):
                args = values.copy()
                args[index] = invalid
                with self.assertRaisesRegex(ValueError, '^Invalid outbox event$'):
                    Event(*args)

    def test_creation_and_later_revision_are_immutable(self):
        from dataclasses import FrozenInstanceError
        from forge.outbox import Event
        event = Event(*(UUID(int=n) for n in range(6, 11)), 'department.created', 0, 1)
        self.assertEqual((event.organization_id, event.revision), (UUID(int=7), 1))
        with self.assertRaises(FrozenInstanceError):
            event.revision = 2

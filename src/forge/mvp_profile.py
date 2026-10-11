"""Reviewed MVP schema profile layered on the retained 0018 gateway profile.

The retained demo lists in ``dev_accounts_gateway`` (ADDITIONS, CHECKPOINTS,
PROFILE) are deliberately never mutated: existing demos keep working at 0018.
Every MVP migration appends one schema-only checkpoint, authored from reviewed
migration bytes on PG17 and proven equal for a fresh apply and an upgrade from the
previous checkpoint. Checkpoints are static; nothing is learned at runtime.
"""
from forge.dev_accounts_gateway import ADDITIONS, CHECKPOINTS

ORIGIN_MIGRATION = '0019_gateway_origin.sql'
MVP_ADDITIONS = (*ADDITIONS, ORIGIN_MIGRATION)
MVP_PROFILE = '0001-0005+0010-0019/PG17'

# Schema fingerprint after 0019 (F19): fresh apply of 0001-0005+0010-0019 and upgrade
# from the 0018 profile were proven identical on the owned PG17 harness.
F19 = '366249318981b950df80c7e958543877e9d2d83f0dae1b14b907a18b39df9d87'

MVP_CHECKPOINTS = (*CHECKPOINTS, F19)

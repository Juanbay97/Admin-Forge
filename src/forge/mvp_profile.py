"""Reviewed MVP schema profile layered on the retained 0018 gateway profile.

The retained demo lists in ``dev_accounts_gateway`` (ADDITIONS, CHECKPOINTS,
PROFILE) are deliberately never mutated: existing demos keep working at 0018.
Every MVP migration appends one schema-only checkpoint, authored from reviewed
migration bytes on PG17 and proven equal for a fresh apply and an upgrade from the
previous checkpoint. Checkpoints are static; nothing is learned at runtime.
"""
from forge.dev_accounts_gateway import ADDITIONS, CHECKPOINTS

ORIGIN_MIGRATION = '0019_gateway_origin.sql'
DIRECTORY_MIGRATION = '0020_directory_identity.sql'
DEPARTMENT_MIGRATION = '0021_department_directory.sql'
MEMBER_DIRECTORY_MIGRATION = '0022_member_directory.sql'
MVP_ADDITIONS = (*ADDITIONS, ORIGIN_MIGRATION, DIRECTORY_MIGRATION, DEPARTMENT_MIGRATION,
                 MEMBER_DIRECTORY_MIGRATION)
MVP_PROFILE = '0001-0005+0010-0022/PG17'

# Schema fingerprint after 0019 (F19): fresh apply of 0001-0005+0010-0019 and upgrade
# from the 0018 profile were proven identical on the owned PG17 harness.
F19 = '366249318981b950df80c7e958543877e9d2d83f0dae1b14b907a18b39df9d87'

# Schema fingerprint after 0020 (F20): fresh apply of 0001-0005+0010-0020 and upgrade
# from the 0019 profile were proven identical on the owned PG17 harness.
F20 = 'eb61cb72599654d7a1e7d959bb323e3a398d5c0197ee404e545ee83e1befe672'

# Schema fingerprint after 0021 (F21): fresh apply of 0001-0005+0010-0021 and upgrade
# from the 0020 profile were proven identical on the owned PG17 harness.
F21 = 'bcb3ce1de893d3a08a29ad2dade5b21399e38dc98a3182db1ea16dcfb6faaaeb'

# Schema fingerprint after 0022 (F22): fresh apply of 0001-0005+0010-0022 and upgrade
# from the 0021 profile were proven identical on the owned PG17 harness.
F22 = '4df89fdf39ff60745dfa6622d90560bd2607ead597675928a4d4190605d06f5b'

MVP_CHECKPOINTS = (*CHECKPOINTS, F19, F20, F21, F22)

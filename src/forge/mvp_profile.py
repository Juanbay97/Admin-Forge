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
MEMBER_LIFECYCLE_MIGRATION = '0023_member_lifecycle.sql'
SCOPED_REVOCATION_MIGRATION = '0024_scoped_session_revocation.sql'
ORG_BRANDING_MIGRATION = '0025_org_branding.sql'
ORG_BRANDING_CODE_MIGRATION = '0026_branding_member_code.sql'
GATEWAY_ORIGIN_CONFIG_MIGRATION = '0027_gateway_origin_config.sql'
PLATFORM_SCOPE_MIGRATION = '0028_platform_scope.sql'
PLATFORM_MFA_MIGRATION = '0029_platform_mfa.sql'
COMPANY_LIFECYCLE_MIGRATION = '0030_company_lifecycle.sql'
PLATFORM_OPERATIONS_MIGRATION = '0031_platform_company_operations.sql'
GATEWAY_KEY_POOL_MIGRATION = '0032_gateway_key_pool.sql'
GATEWAY_KEY_ROUTING_MIGRATION = '0033_gateway_key_routing.sql'
GATEWAY_ADMIN_READONLY_MIGRATION = '0034_gateway_admin_readonly.sql'
USAGE_EVENTS_MIGRATION = '0035_usage_events.sql'
MODEL_PRICES_MIGRATION = '0036_model_prices.sql'
USAGE_READS_MIGRATION = '0037_usage_reads.sql'
CAPABILITY_CATALOG_MIGRATION = '0038_capability_catalog.sql'
CAPABILITY_POLICY_MIGRATION = '0039_capability_policy.sql'
TOOL_INVOCATION_LOG_MIGRATION = '0040_tool_invocation_log.sql'
CONNECTOR_SECRETS_MIGRATION = '0041_connector_secrets.sql'
USAGE_ME_MIGRATION = '0042_usage_me.sql'
PLATFORM_MEMBERS_MIGRATION = '0043_platform_members.sql'
PLATFORM_OVERVIEW_MIGRATION = '0044_platform_overview.sql'
MVP_ADDITIONS = (*ADDITIONS, ORIGIN_MIGRATION, DIRECTORY_MIGRATION, DEPARTMENT_MIGRATION,
                 MEMBER_DIRECTORY_MIGRATION, MEMBER_LIFECYCLE_MIGRATION, SCOPED_REVOCATION_MIGRATION,
                 ORG_BRANDING_MIGRATION, ORG_BRANDING_CODE_MIGRATION, GATEWAY_ORIGIN_CONFIG_MIGRATION,
                 PLATFORM_SCOPE_MIGRATION, PLATFORM_MFA_MIGRATION, COMPANY_LIFECYCLE_MIGRATION,
                 PLATFORM_OPERATIONS_MIGRATION, GATEWAY_KEY_POOL_MIGRATION, GATEWAY_KEY_ROUTING_MIGRATION,
                 GATEWAY_ADMIN_READONLY_MIGRATION, USAGE_EVENTS_MIGRATION, MODEL_PRICES_MIGRATION, USAGE_READS_MIGRATION, CAPABILITY_CATALOG_MIGRATION, CAPABILITY_POLICY_MIGRATION, TOOL_INVOCATION_LOG_MIGRATION, CONNECTOR_SECRETS_MIGRATION, USAGE_ME_MIGRATION, PLATFORM_MEMBERS_MIGRATION, PLATFORM_OVERVIEW_MIGRATION)
MVP_PROFILE = '0001-0005+0010-0044/PG17'

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

# Schema fingerprint after 0023 (F23): fresh apply of 0001-0005+0010-0023 and upgrade
# from the 0022 profile were proven identical on the owned PG17 harness.
F23 = 'e025d612b3b39bc7ef01d22feca98ec80e8231594b9fe8aa5d62d391d9199c0d'

# Schema fingerprint after 0024 (F24): fresh apply of 0001-0005+0010-0024 and upgrade
# from the 0023 profile were proven identical on the owned PG17 harness.
F24 = '69bab9f16d2c6a2b1414b6d47dfdef1c4519344e9d861fb76c8cef87c16bb899'

# Schema fingerprint after 0025 (F25): fresh apply of 0001-0005+0010-0025 and upgrade
# from the 0024 profile were proven identical on the owned PG17 harness.
F25 = '68ae4dd4edb8bbbd5822b3d082e93804e02de18fdde6d7ea8ec2ba282d37fd0b'

# Schema fingerprint after 0026 (F26): fresh apply of 0001-0005+0010-0026 and upgrade
# from the 0025 profile were proven identical on the owned PG17 harness.
F26 = 'f78ca72a7497ef3c96236b70641cad92c3a1d2df183946873a8d3e1f73c2e539'

# Schema fingerprint after 0027 (F27): fresh apply of 0001-0005+0010-0027 and upgrade
# from the 0026 profile were proven identical on the owned PG17 harness.
F27 = 'c88a837bc19b63a37919b77838bf7ee818bc129728d11c776a01bd7197985123'

# Schema fingerprint after 0028 (F28): fresh apply of 0001-0005+0010-0028 and upgrade
# from the 0027 profile were proven identical on the owned PG17 harness.
F28 = 'f6b2ffc3dfca19b0044cb66d9b80ca9c872bbeaac5732098ac4fe30da1146893'

# Schema fingerprint after 0029 (F29): fresh apply of 0001-0005+0010-0029 and upgrade
# from the 0028 profile were proven identical on the owned PG17 harness.
F29 = '75687ff6c39abfdcd5fa9500beb9e416756a3e4900833882c22810e30583444c'

# Schema fingerprint after 0030 (F30): fresh apply of 0001-0005+0010-0030 and upgrade
# from the 0029 profile were proven identical on the owned PG17 harness.
F30 = 'cc2e5ad1a6a9f2caf841bf88a14a1ed09e41feb33a75b93d4a2bcb88c3b10742'

# Schema fingerprint after 0031 (F31): fresh apply of 0001-0005+0010-0031 and upgrade
# from the 0030 profile were proven identical on the owned PG17 harness.
F31 = 'a2514ac85bcc0fe78cab7f506d35bc68037356fd0d4e638698e39304645617b9'

# Schema fingerprint after 0032 (F32): fresh apply of 0001-0005+0010-0032 and upgrade
# from the 0031 profile were proven identical on the owned PG17 harness.
F32 = 'a92e1a907d3f61a1b24d2bd7c8b77947bb3b365d6da3d70a1dd7d1aa58af8824'

# Schema fingerprint after 0033 (F33): fresh apply of 0001-0005+0010-0033 and upgrade
# from the 0032 profile were proven identical on the owned PG17 harness.
F33 = 'a8a8ba3bf638b13bd263a6ac42b15e62f946cb93dbcabaff4ac1d15e518ab496'

# Schema fingerprint after 0034 (F34): fresh apply of 0001-0005+0010-0034 and upgrade
# from the 0033 profile were proven identical on the owned PG17 harness.
F34 = '3311197cc535225245a72b9e79e6aa79269647be788e83cbb5075457d81e2336'

# Schema fingerprint after 0035 (F35): fresh apply of 0001-0005+0010-0035 and upgrade
# from the 0034 profile were proven identical on the owned PG17 harness.
F35 = '6aa584d9de7a372b21284002637365511c4cb2f8bddf9986bb060aeb7769b692'

# Schema fingerprint after 0036 (F36): fresh apply of 0001-0005+0010-0036 and upgrade
# from the 0035 profile were proven identical on the owned PG17 harness.
F36 = '91516e6f3ff266c0ea6e22e029767d6412b7dd77a2bd80313812559a53e32a87'

# Schema fingerprint after 0037 (F37): fresh apply of 0001-0005+0010-0037 and upgrade
# from the 0036 profile were proven identical on the owned PG17 harness.
F37 = 'b16b4f68f788ed4930fde663027924c802e8b547167a47f10159928d0538c653'

# Schema fingerprint after 0038 (F38): fresh apply of 0001-0005+0010-0038 and upgrade
# from the 0037 profile were proven identical on the owned PG17 harness.
F38 = '63a4be7d1a97e2ad992b7625b8e7597cad079a80d903368f1e0b4babdd0c4039'

# Schema fingerprint after 0039 (F39): fresh apply of 0001-0005+0010-0039 and upgrade
# from the 0038 profile were proven identical on the owned PG17 harness.
F39 = 'ef2968ba23e3cbe14e7d36631d6b33d6369c9c74834e15a4babf449de581727a'

# Schema fingerprint after 0040 (F40): fresh apply of 0001-0005+0010-0040 and upgrade
# from the 0039 profile were proven identical on the owned PG17 harness.
F40 = '2861e99aaa35ced909a221972062236649c2ba2ef5e7031845974ee58cfc5062'

# Schema fingerprint after 0041 (F41): fresh apply of 0001-0005+0010-0041 and upgrade
# from the 0040 profile were proven identical on the owned PG17 harness.
F41 = '45358432eb8ab4d5aa729b163e54ba825a9d28b26ba59f700876863ee659fe68'

# Schema fingerprint after 0042 (F42): fresh apply of 0001-0005+0010-0042 and upgrade
# from the 0041 profile were proven identical on the owned PG17 harness.
F42 = '758fc3e249eedeb68230e045ee53b32db81e42cae68afd3ffff4c03127dee127'

# Schema fingerprint after 0043 (F43): fresh apply of 0001-0005+0010-0043 and upgrade
# from the 0042 profile were proven identical on the owned PG17 harness.
F43 = 'eb4c7642e9b14785b135877d064f110a91a863d0316392b578f7ae4a8ffc9d13'

# Schema fingerprint after 0044 (F44): fresh apply of 0001-0005+0010-0044 and upgrade
# from the 0043 profile were proven identical on the owned PG17 harness.
F44 = '3d821d280540bcd8ed59fa70e899d7dcb21baef5b9f04bdb2a113aa8617addaa'

MVP_CHECKPOINTS = (*CHECKPOINTS, F19, F20, F21, F22, F23, F24, F25, F26, F27, F28, F29, F30, F31, F32, F33, F34, F35, F36, F37, F38, F39, F40, F41, F42, F43, F44)

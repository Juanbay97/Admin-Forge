"""Separate opt-in exact catalog attestation; never relax legacy readiness."""
import hashlib
import json
from psycopg.rows import tuple_row
from psycopg.pq import TransactionStatus
from forge.account_store import EnrollmentConnection
from forge.postgres import _ROLE_CHECK

# Authored from the pristine owned migration fixture, never learned at runtime.
# PostgreSQL17 catalog projection, captured on owned PostgreSQL17.11.
# Names, not transient OIDs, normalize ACLs/policies; source and grants are exact.
# Supported installation: actual0001–0004 plus0013–0014, no optional extensions.
_EXPECTED_SHA256 = '713d5fd1851f911ab12ec3dbb1a813b4ec3f549aa27940902b9881a1d50e297c'

_CATALOG = """
SELECT jsonb_build_object(
 'server_major',current_setting('server_version_num')::integer/10000,
 'schema',(SELECT jsonb_build_array(pg_get_userbyid(nspowner),
  (SELECT jsonb_agg(jsonb_build_array(pg_get_userbyid(grantor),CASE WHEN grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(grantee) END,privilege_type,is_grantable)
   ORDER BY CASE WHEN grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(grantee) END,privilege_type,pg_get_userbyid(grantor)) FROM aclexplode(coalesce(nspacl,acldefault('n',nspowner)))))
  FROM pg_namespace WHERE nspname='forge'),
 'roles',(SELECT jsonb_agg(jsonb_build_array(rolname,rolsuper,rolinherit,rolcreaterole,rolcreatedb,rolreplication,rolbypassrls)
   ORDER BY rolname) FROM pg_roles WHERE rolname LIKE 'forge_%'),
 'edges',(SELECT coalesce(jsonb_agg(jsonb_build_array(pg_get_userbyid(roleid),pg_get_userbyid(member),admin_option) ORDER BY pg_get_userbyid(roleid),pg_get_userbyid(member)),'[]'::jsonb)
   FROM pg_auth_members WHERE pg_get_userbyid(roleid) LIKE 'forge_%' OR pg_get_userbyid(member) LIKE 'forge_%'),
 'relations',(SELECT jsonb_agg(jsonb_build_object(
   'name',t.relname,'kind',t.relkind,'owner',pg_get_userbyid(t.relowner),'rls',t.relrowsecurity,'force',t.relforcerowsecurity,
   'acl',(SELECT jsonb_agg(jsonb_build_array(pg_get_userbyid(grantor),CASE WHEN grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(grantee) END,privilege_type,is_grantable) ORDER BY CASE WHEN grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(grantee) END,privilege_type,pg_get_userbyid(grantor))
     FROM aclexplode(coalesce(t.relacl,acldefault('r',t.relowner)))),
   'columns',(SELECT jsonb_agg(jsonb_build_array(a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,pg_get_expr(d.adbin,d.adrelid),
     (SELECT jsonb_agg(jsonb_build_array(CASE WHEN grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(grantee) END,privilege_type,is_grantable) ORDER BY CASE WHEN grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(grantee) END,privilege_type,pg_get_userbyid(grantor)) FROM aclexplode(a.attacl)))
     ORDER BY a.attnum) FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
     WHERE a.attrelid=t.oid AND a.attnum>0 AND NOT a.attisdropped),
   'constraints',(SELECT jsonb_agg(jsonb_build_array(c.conname,c.contype,c.convalidated,c.condeferrable,c.condeferred,pg_get_constraintdef(c.oid)) ORDER BY c.conname) FROM pg_constraint c WHERE c.conrelid=t.oid),
   'policies',(SELECT jsonb_agg(jsonb_build_array(p.polname,p.polcmd,p.polpermissive,
     (SELECT jsonb_agg(CASE WHEN r=0 THEN 'PUBLIC' ELSE pg_get_userbyid(r) END ORDER BY CASE WHEN r=0 THEN 'PUBLIC' ELSE pg_get_userbyid(r) END) FROM unnest(p.polroles) r),pg_get_expr(p.polqual,p.polrelid),pg_get_expr(p.polwithcheck,p.polrelid)) ORDER BY p.polname) FROM pg_policy p WHERE p.polrelid=t.oid),
   'triggers',(SELECT jsonb_agg(jsonb_build_array(g.tgname,g.tgenabled,g.tgtype,pg_get_triggerdef(g.oid)) ORDER BY g.tgname) FROM pg_trigger g WHERE g.tgrelid=t.oid AND NOT g.tgisinternal),
   'indexes',(SELECT jsonb_agg(pg_get_indexdef(i.indexrelid) ORDER BY pg_get_indexdef(i.indexrelid)) FROM pg_index i WHERE i.indrelid=t.oid)
 ) ORDER BY t.relname) FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace WHERE n.nspname='forge' AND t.relkind IN ('r','p','v','m','S')),
 'functions',(SELECT jsonb_agg(jsonb_build_array(p.proname,pg_get_function_identity_arguments(p.oid),pg_get_function_result(p.oid),pg_get_userbyid(p.proowner),p.prosecdef,p.proleakproof,p.provolatile,p.proconfig,p.prosrc,
   (SELECT jsonb_agg(jsonb_build_array(pg_get_userbyid(grantor),CASE WHEN grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(grantee) END,privilege_type,is_grantable) ORDER BY CASE WHEN grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(grantee) END,privilege_type,pg_get_userbyid(grantor)) FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner)))))
   ORDER BY p.proname,pg_get_function_identity_arguments(p.oid)) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='forge')
)
"""


def catalog_fingerprint(cursor) -> str:
    """Schema-only projection: no business rows, passwords, tokens or credentials."""
    cursor.execute(_CATALOG)
    document=cursor.fetchone()[0]
    encoded=json.dumps(document,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


_SERVICE_PRIVILEGES = """
SELECT NOT has_database_privilege(current_user,current_database(),'CREATE')
 AND NOT has_database_privilege(current_user,current_database(),'TEMP')
 AND NOT has_schema_privilege(current_user,'public','CREATE')
 AND NOT has_schema_privilege(current_user,'forge','CREATE')
 -- Internal owners must remain NOLOGIN. Connection-role LOGIN is intentional
 -- and is not included in this authority-only check or blanket rejected.
 AND (SELECT count(*)=2 AND bool_and(NOT rolcanlogin) FROM pg_roles
      WHERE rolname IN ('forge_migrator','forge_enrollment_authority'))
"""


class AccountReadiness:
    """Explicit account-service and read-only bootstrap pools; no ambient config."""
    def __init__(self,account_pool,bootstrap_pool,*,acquisition_timeout=1.0):
        self._accounts=EnrollmentConnection(account_pool,acquisition_timeout=acquisition_timeout,role='forge_account_service')
        self._bootstrap=bootstrap_pool
        self._timeout=acquisition_timeout

    def check(self) -> bool:
        if _EXPECTED_SHA256 is None:
            return False
        try:
            with self._accounts.cursor() as cursor:
                cursor.execute(_SERVICE_PRIVILEGES)
                if cursor.fetchone() != (True,):
                    return False
                if catalog_fingerprint(cursor)!=_EXPECTED_SHA256:
                    return False
            with self._bootstrap.connection(timeout=self._timeout) as conn:
                if not conn.autocommit or conn.info.transaction_status is not TransactionStatus.IDLE:
                    return False
                with conn.transaction(),conn.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL statement_timeout='5s'")
                    cursor.execute(_ROLE_CHECK)
                    return cursor.fetchone()==(True,)
        except Exception:
            return False

"""Restricted synchronous publication transaction; caller composition owns pools."""
from math import isfinite
from uuid import UUID, uuid4
import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row

from forge.authorization import AuthorizationSnapshot, permits
from forge.catalog_publication import (
    PublicationRequest, PublicationResult, PublicationDenied, PublicationConflict,
    PublicationUnavailable, valid_principal, valid_request,
)
from forge.foundation import MembershipStatus
from forge.model_catalog_store import read_catalog, encode_catalog
from forge.outbox import Event
from forge.outbox_store import record_event
from forge.postgres import _EMPTY_CONTEXT

_ROLE = """
SELECT current_user='forge_config_publisher' AND session_user=current_user
 AND NOT (r.rolsuper OR r.rolinherit OR r.rolbypassrls OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication)
 AND NOT EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=r.oid)
 AND NOT EXISTS(SELECT 1 FROM pg_catalog.pg_class WHERE relowner=r.oid)
 AND NOT has_schema_privilege(current_user,'forge','CREATE')
 AND NOT has_schema_privilege(current_user,'public','CREATE')
 AND NOT has_database_privilege(current_user,current_database(),'CREATE,TEMP')
 AND current_setting('row_security')='on'
 AND current_setting('transaction_isolation')='read committed'
 AND NOT EXISTS(
   SELECT 1 FROM pg_catalog.pg_class t JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
   WHERE n.nspname='forge' AND t.relkind='r' AND (
     NOT t.relrowsecurity OR NOT t.relforcerowsecurity
     OR has_table_privilege(current_user,t.oid,'SELECT') IS DISTINCT FROM
        (t.relname IN ('model_catalog_snapshots','active_model_catalogs','catalog_publication_operations'))
     OR has_table_privilege(current_user,t.oid,'INSERT') IS DISTINCT FROM
        (t.relname IN ('outbox_events','active_model_catalogs','catalog_publication_operations'))
     OR has_table_privilege(current_user,t.oid,'UPDATE') IS DISTINCT FROM (t.relname='active_model_catalogs')
     OR has_table_privilege(current_user,t.oid,'DELETE,TRUNCATE,REFERENCES,TRIGGER')
     OR has_table_privilege(current_user,t.oid,
         'SELECT WITH GRANT OPTION,INSERT WITH GRANT OPTION,UPDATE WITH GRANT OPTION')
     OR has_any_column_privilege(current_user,t.oid,
         'SELECT WITH GRANT OPTION,INSERT WITH GRANT OPTION,UPDATE WITH GRANT OPTION')
     OR (t.relname NOT IN ('model_catalog_snapshots','active_model_catalogs','catalog_publication_operations')
         AND has_any_column_privilege(current_user,t.oid,'SELECT'))
     OR (t.relname NOT IN ('outbox_events','active_model_catalogs','catalog_publication_operations')
         AND has_any_column_privilege(current_user,t.oid,'INSERT'))
     OR (t.relname<>'active_model_catalogs' AND has_any_column_privilege(current_user,t.oid,'UPDATE'))
     OR has_any_column_privilege(current_user,t.oid,'REFERENCES')))
FROM pg_catalog.pg_roles r WHERE r.rolname=current_user
"""


class PostgresCatalogPublisher:
    def __init__(self, pool, *, acquisition_timeout=1):
        if (type(acquisition_timeout) not in (int, float)
                or not 0 < acquisition_timeout <= 30 or not isfinite(acquisition_timeout)):
            raise ValueError("Invalid catalog acquisition timeout.")
        self._pool = pool
        self._timeout = float(acquisition_timeout)

    def _publish(self, principal, member, request: PublicationRequest):
        if not valid_principal(principal) or not valid_request(request) or type(member) is not UUID:
            raise PublicationDenied()
        try:
            with self._pool.connection(timeout=self._timeout) as conn:
                if not conn.autocommit or conn.info.transaction_status is not TransactionStatus.IDLE:
                    raise PublicationUnavailable()
                with conn.transaction(), conn.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL statement_timeout='3s'")
                    cursor.execute("SET LOCAL lock_timeout='1s'")
                    cursor.execute("SET LOCAL search_path=pg_catalog")
                    for query in (_EMPTY_CONTEXT, _ROLE):
                        cursor.execute(query)
                        if cursor.fetchone() != (True,):
                            raise PublicationUnavailable()
                    for key, value in (("organization", request.organization_id), ("provider", "entra"),
                                       ("issuer", principal.issuer), ("subject", principal.oid)):
                        cursor.execute("SELECT set_config(%s,%s,true)", ("forge."+key, str(value)))
                    cursor.execute("SELECT forge.lock_catalog_authority(%s,%s,%s,%s)",
                                   (request.organization_id, member, UUID(principal.tid), UUID(principal.oid)))
                    revision = cursor.fetchone()[0]
                    locked = AuthorizationSnapshot(principal.identity, request.organization_id, member,
                        revision, frozenset({"organization_admin"}), MembershipStatus.ACTIVE, True)
                    if not permits(locked, "models.publish"):
                        raise PublicationDenied()
                    target = request.expected_revision+1
                    catalog = read_catalog(conn, request.organization_id, request.router_binding_id, target)
                    if catalog is None or encode_catalog(catalog)[1] != request.payload_sha256:
                        raise PublicationConflict()
                    # Immutable replay is read only after fresh locked authorization.
                    cursor.execute("SELECT actor_id,router_binding_id,expected_revision,catalog_revision,"
                        "payload_sha256,event_id FROM forge.catalog_publication_operations "
                        "WHERE organization_id=%s AND operation_id=%s",
                        (request.organization_id, request.operation_id))
                    replay = cursor.fetchone()
                    if replay is not None:
                        if replay[:5] != (member, request.router_binding_id, request.expected_revision,
                                         target, request.payload_sha256):
                            raise PublicationConflict()
                        return PublicationResult(request.organization_id, request.router_binding_id,
                                                 request.operation_id, replay[5], target)
                    cursor.execute("SELECT catalog_revision FROM forge.active_model_catalogs "
                                   "WHERE organization_id=%s FOR UPDATE", (request.organization_id,))
                    current = cursor.fetchone()
                    if (0 if current is None else current[0]) != request.expected_revision:
                        raise PublicationConflict()
                    event = uuid4()
                    record_event(conn, Event(event, request.organization_id, member, request.operation_id,
                                             request.router_binding_id, "model_catalog.published",
                                             request.expected_revision, target))
                    if current is None:
                        cursor.execute("INSERT INTO forge.active_model_catalogs "
                            "(organization_id,router_binding_id,catalog_revision,event_id) VALUES(%s,%s,%s,%s)",
                            (request.organization_id, request.router_binding_id, target, event))
                    else:
                        cursor.execute("UPDATE forge.active_model_catalogs SET router_binding_id=%s,"
                            "catalog_revision=%s,event_id=%s WHERE organization_id=%s AND catalog_revision=%s",
                            (request.router_binding_id, target, event, request.organization_id,
                             request.expected_revision))
                        if cursor.rowcount != 1:
                            raise PublicationConflict()
                    cursor.execute("INSERT INTO forge.catalog_publication_operations "
                        "(operation_id,organization_id,actor_id,router_binding_id,expected_revision,"
                        "catalog_revision,payload_sha256,event_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                        (request.operation_id, request.organization_id, member, request.router_binding_id,
                         request.expected_revision, target, request.payload_sha256, event))
                    result = PublicationResult(request.organization_id, request.router_binding_id,
                                               request.operation_id, event, target)
                return result  # Commit and deferred checks completed before returning.
        except (PublicationDenied, PublicationConflict, PublicationUnavailable):
            raise
        except psycopg.IntegrityError:
            raise PublicationConflict() from None
        except Exception:
            raise PublicationUnavailable() from None

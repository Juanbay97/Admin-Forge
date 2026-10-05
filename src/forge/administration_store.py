"""Atomic internal designation over a separately provisioned restricted sync pool.

Only InitialAdministratorService may supply operator authority. Constructing the
port's dataclasses is NOT authentication; there is no HTTP/runtime wiring here.
"""
from uuid import UUID, uuid4
from psycopg.pq import TransactionStatus
from psycopg.rows import tuple_row
from forge.administration import (
    DeploymentOperator, DesignationRequest, DesignationResult, DesignationDenied,
    DesignationConflict, DesignationUnavailable, valid_operator, valid_request,
)
from forge.postgres import (
    _EMPTY_CONTEXT, _DESIGNATOR_CHECK, _DESIGNATION_SCHEMA,
    _DESIGNATION_FUNCTION_SOURCES,
)

_REPLAY = """SELECT organization_id,membership_id,request_id,actor_id,target_tenant_id,
    expected_revision,revision,event_id FROM forge.initial_admin_designations
    WHERE organization_id=%s AND request_id=%s"""
_CLAIM = """INSERT INTO forge.initial_admin_designations
    (organization_id,membership_id,request_id,actor_id,target_tenant_id,
     expected_revision,revision,event_id)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING event_id"""
_EVENT = """INSERT INTO forge.initial_admin_outbox
    (event_id,schema_version,organization_id,actor_id,actor_type,source,event_type,
     request_id,resource_type,resource_id,outcome,previous_revision,revision,metadata)
    VALUES (%s,1,%s,%s,'deployment_operator','server','membership.initial_admin_designated',
            %s,'membership',%s,'succeeded',%s,%s,
            jsonb_build_object('role','organization_admin','previous_revision',%s::bigint,'revision',%s::bigint))"""

class PostgresInitialAdministratorStore:
    def __init__(self, pool, *, acquisition_timeout=1):
        if type(acquisition_timeout) not in (int,float) or not 0<acquisition_timeout<=30:
            raise ValueError("Initial designation acquisition timeout is invalid.")
        self._pool,self._timeout=pool,float(acquisition_timeout)

    @staticmethod
    def _replay(cursor,operator,request,tenants):
        cursor.execute(_REPLAY,(request.organization_id,request.operation_id))
        row=cursor.fetchone()
        if row is None:return None
        org,member,operation,actor,tenant,expected,revision,event=row
        if (org,member,operation,actor,expected)!=(request.organization_id,
                request.membership_id,request.operation_id,operator.actor_id,request.expected_revision):
            raise DesignationConflict()
        if tenant not in tenants:raise DesignationDenied()
        return DesignationResult(org,member,operation,event,revision)

    def _designate(self,operator,request,allowed_tenants):
        if (not valid_operator(operator) or not valid_request(request)
                or type(allowed_tenants) is not frozenset or not 1<=len(allowed_tenants)<=64
                or any(type(t) is not UUID for t in allowed_tenants)):
            raise DesignationDenied()
        try:
            with self._pool.connection(timeout=self._timeout) as conn:
                if not conn.autocommit or conn.info.transaction_status is not TransactionStatus.IDLE:
                    raise DesignationUnavailable()
                with conn.transaction(),conn.cursor(row_factory=tuple_row) as cursor:
                    cursor.execute("SET LOCAL statement_timeout='3s'")
                    cursor.execute("SET LOCAL lock_timeout='1s'")
                    cursor.execute("SET LOCAL search_path=pg_catalog")
                    for query,params in ((_EMPTY_CONTEXT,None),(_DESIGNATOR_CHECK,None),
                            (_DESIGNATION_SCHEMA,_DESIGNATION_FUNCTION_SOURCES)):
                        cursor.execute(query,params)
                        row=cursor.fetchone()
                        if row is None or row[0] is not True:raise DesignationUnavailable()
                    for key,value in (("organization",request.organization_id),
                            ("member",request.membership_id),("actor",operator.actor_id),
                            ("request",request.operation_id)):
                        cursor.execute("SELECT set_config(%s,%s,true)",
                            ("forge.designation_"+key,str(value)))
                    replay=self._replay(cursor,operator,request,allowed_tenants)
                    if replay is not None:return replay
                    # Lookup only to populate invoker identity scope. Reload under
                    # lock after the permanent claim, never trust this read as a reservation.
                    cursor.execute("SELECT identity_id FROM forge.memberships "
                        "WHERE organization_id=%s AND id=%s",(request.organization_id,request.membership_id))
                    row=cursor.fetchone()
                    if row is None:raise DesignationDenied()
                    identity_id=row[0]
                    cursor.execute("SELECT set_config('forge.designation_identity',%s,true)",(str(identity_id),))
                    cursor.execute("SELECT entra_tenant_id FROM forge.identities WHERE id=%s",(identity_id,))
                    row=cursor.fetchone()
                    if row is None or row[0] not in allowed_tenants:raise DesignationDenied()
                    tenant=row[0];event=uuid4()
                    cursor.execute(_CLAIM,(request.organization_id,request.membership_id,
                        request.operation_id,operator.actor_id,tenant,request.expected_revision,
                        request.expected_revision+1,event))
                    if cursor.fetchone() is None:
                        replay=self._replay(cursor,operator,request,allowed_tenants)
                        if replay is not None:return replay
                        raise DesignationConflict()
                    cursor.execute("""SELECT m.identity_id,m.revision,i.entra_tenant_id
                        FROM forge.memberships m JOIN forge.organizations o ON o.id=m.organization_id
                        JOIN forge.identities i ON i.id=m.identity_id
                        WHERE m.organization_id=%s AND m.id=%s AND m.status='active'
                        FOR UPDATE OF m""",(request.organization_id,request.membership_id))
                    row=cursor.fetchone()
                    if row is None or row[0]!=identity_id or row[2]!=tenant:raise DesignationDenied()
                    if row[1]!=request.expected_revision:raise DesignationConflict()
                    cursor.execute("SELECT 1 FROM forge.membership_roles WHERE organization_id=%s "
                        "AND role='organization_admin' LIMIT 1",(request.organization_id,))
                    if cursor.fetchone() is not None:raise DesignationConflict()
                    cursor.execute("INSERT INTO forge.membership_roles VALUES(%s,%s,'organization_admin')",
                        (request.organization_id,request.membership_id))
                    cursor.execute("UPDATE forge.memberships SET revision=revision+1 "
                        "WHERE organization_id=%s AND id=%s AND revision=%s RETURNING revision",
                        (request.organization_id,request.membership_id,request.expected_revision))
                    row=cursor.fetchone()
                    if row is None or row[0]!=request.expected_revision+1:raise DesignationConflict()
                    cursor.execute(_EVENT,(event,request.organization_id,operator.actor_id,
                        request.operation_id,request.membership_id,request.expected_revision,row[0],
                        request.expected_revision,row[0]))
                    # Deferred marker/event FK is checked on context exit before return.
                    return DesignationResult(request.organization_id,request.membership_id,
                        request.operation_id,event,row[0])
        except (DesignationDenied,DesignationConflict,DesignationUnavailable):raise
        except Exception:raise DesignationUnavailable() from None

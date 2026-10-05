"""Authenticated internal initial designation; no endpoints or deployment defaults."""
from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from forge.entra import EntraOperationalError, EntraTokenValidator

class DesignationDenied(RuntimeError):
    def __init__(self): super().__init__("Initial designation denied.")
class DesignationConflict(RuntimeError):
    def __init__(self): super().__init__("Initial designation conflicts.")
class DesignationUnavailable(RuntimeError):
    def __init__(self): super().__init__("Initial designation unavailable.")

@dataclass(frozen=True, repr=False)
class DeploymentOperator:
    issuer: str
    tenant_id: UUID
    object_id: UUID
    actor_id: UUID

@dataclass(frozen=True, repr=False)
class DesignationRequest:
    organization_id: UUID
    membership_id: UUID
    operation_id: UUID
    expected_revision: int

@dataclass(frozen=True, repr=False)
class DesignationResult:
    organization_id: UUID
    membership_id: UUID
    operation_id: UUID
    event_id: UUID
    revision: int
    audit_publication: str = "pending"

def valid_request(value):
    return (type(value) is DesignationRequest
            and all(type(getattr(value,k)) is UUID for k in
                    ("organization_id","membership_id","operation_id"))
            and type(value.expected_revision) is int
            and 0 < value.expected_revision <= 2**63-2)

def valid_operator(value):
    return (type(value) is DeploymentOperator
            and all(type(getattr(value,k)) is UUID for k in
                    ("tenant_id","object_id","actor_id"))
            and type(value.issuer) is str
            and value.issuer == "https://login.microsoftonline.com/"+str(value.tenant_id)+"/v2.0")

@dataclass(frozen=True, repr=False)
class DesignationConfiguration:
    operators: tuple[DeploymentOperator, ...]
    organization_tenants: object

    def __post_init__(self):
        try:
            if type(self.operators) not in (tuple,list) or len(self.operators)>64:
                raise ValueError
            operators=tuple(self.operators)
            if any(not valid_operator(v) for v in operators):
                raise ValueError
            keys=[(v.issuer,v.tenant_id,v.object_id) for v in operators]
            if len(set(keys))!=len(keys): raise ValueError
            if not isinstance(self.organization_tenants,(dict,MappingProxyType)):
                raise ValueError
            if len(self.organization_tenants)>256:raise ValueError
            targets={}
            for org,tenants in self.organization_tenants.items():
                if (type(org) is not UUID or type(tenants) not in (set,frozenset)
                        or not 1<=len(tenants)<=64 or any(type(t) is not UUID for t in tenants)):
                    raise ValueError
                targets[org]=frozenset(tenants)
            object.__setattr__(self,"operators",operators)
            object.__setattr__(self,"organization_tenants",MappingProxyType(targets))
        except Exception:
            raise ValueError("Initial designation configuration is invalid.") from None

class InitialAdministratorService:
    """Trust deployment composition, never a caller-supplied principal/actor.

    The public service boundary accepts only a raw token and typed request. Its
    actual Entra validator authenticates each attempt, including response-loss
    replay. The private store port receives only server-derived operator authority.
    """
    def __init__(self, validator, store, configuration=None):
        if type(validator) is not EntraTokenValidator:
            raise ValueError("Initial designation validator is invalid.")
        if configuration is not None and type(configuration) is not DesignationConfiguration:
            raise ValueError("Initial designation configuration is invalid.")
        self._validator,self._store,self._configuration=validator,store,configuration

    def designate(self, token, request):
        cfg=self._configuration
        if (cfg is None or not cfg.operators or not valid_request(request)
                or request.organization_id not in cfg.organization_tenants):
            raise DesignationDenied()
        try: principal=self._validator.validate_principal(token)
        except EntraOperationalError: raise DesignationUnavailable() from None
        if principal is None: raise DesignationDenied()
        operator=next((v for v in cfg.operators if v.issuer==principal.issuer
            and str(v.tenant_id)==principal.tid and str(v.object_id)==principal.oid),None)
        if operator is None: raise DesignationDenied()
        try:
            result=self._store._designate(operator,request,cfg.organization_tenants[request.organization_id])
            if (type(result) is not DesignationResult
                    or (result.organization_id,result.membership_id,result.operation_id)!=
                       (request.organization_id,request.membership_id,request.operation_id)
                    or type(result.revision) is not int or result.revision!=request.expected_revision+1
                    or type(result.event_id) is not UUID or result.audit_publication!="pending"):
                raise DesignationUnavailable()
            return result
        except (DesignationDenied,DesignationConflict,DesignationUnavailable):raise
        except Exception:raise DesignationUnavailable() from None

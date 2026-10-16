"""Explicit opt-in owned-account HTTP composition, never environment discovery."""
from threading import Lock
from time import monotonic
from typing import Annotated, Callable, Protocol, Literal
from uuid import UUID,uuid4

from fastapi import Depends,Request,FastAPI
from fastapi.responses import JSONResponse,StreamingResponse
from pydantic import BaseModel,ConfigDict,Field,field_validator

from forge import contract as forge_contract
from forge.api import BootstrapReader,create_app,ApiFailure,ErrorDetail,ErrorEnvelope,error_response
from forge.account_sessions import AccountSession,SessionService,SessionDenied,LoginThrottled
from forge.accounts import ACCOUNT_ISSUER,PasswordWorkUnavailable
from forge.authorization import AuthorizationSnapshot,valid_snapshot
from forge.foundation import AuthenticatedIdentity
from forge.invitations import InvitationService,InvitationRequest,InvitationDenied,ExistingAccountAuthenticationRequired,InvitationUnavailable
from forge.invitation_delivery import COMPANY_CODE,DeliveryCoordinator
from forge.directory import (DirectoryService,DirectoryDenied,DirectorySuspended,DirectoryConflict,
    DirectoryLastAdmin,DirectoryUnavailable)
from forge.gateway_inference import GatewayInference,TextRequest
from forge.gateway_catalog import GatewayCatalog
from forge.gateway_configuration import (GatewayConfiguration,GatewayDenied,GatewayConflict,GatewayManaged,
    GatewayOutsideCeiling,GatewayUnavailable)


class ReadinessPort(Protocol):
    def check(self) -> bool: ...


class AuthorizationReaderPort(Protocol):
    def read(self, identity: AuthenticatedIdentity, organization_id: str) -> AuthorizationSnapshot | None: ...


def genuine_identity(identity: object) -> bool:
    if (type(identity) is not AuthenticatedIdentity or identity.provider != 'forge'
            or identity.issuer != ACCOUNT_ISSUER):
        return False
    try:
        return str(UUID(identity.subject)) == identity.subject
    except (ValueError, TypeError, AttributeError):
        return False


class InputModel(BaseModel):
    model_config=ConfigDict(extra='forbid')


class LoginBody(InputModel):
    email: Annotated[str,Field(strict=True,min_length=3,max_length=254)]
    password: Annotated[str,Field(strict=True,min_length=15,max_length=1024,repr=False)]


class GatewayBody(InputModel):
    expected_revision: Annotated[int,Field(strict=True,ge=0,le=2**63-3)]
    api_key: Annotated[str,Field(strict=True,min_length=1,max_length=4096,repr=False,json_schema_extra={'writeOnly':True})]
    # Must exactly match the deployment allow-list; omitted means the fixed default origin.
    endpoint: Annotated[str,Field(strict=True,min_length=1,max_length=255)]|None=None


class GatewayResponse(InputModel):
    status: Literal['NOT_CONFIGURED','SAVED_UNVERIFIED']
    revision: Annotated[int,Field(strict=True,ge=0)]
    endpoint: Annotated[str,Field(max_length=255)]


class GatewayReadResponse(GatewayResponse):
    allowed_endpoints: list[str]


class CatalogPublishBody(InputModel):
    operation_id: UUID
    expected_catalogue_revision: Annotated[int,Field(strict=True,ge=0,le=2**63-3)]
    expected_gateway_revision: Annotated[int,Field(strict=True,ge=1,le=2**63-2)]
    aliases: Annotated[dict[str,str],Field(min_length=1,max_length=64)]
    default_alias: Annotated[str,Field(strict=True,min_length=1,max_length=64)]


class UnknownModelResponse(InputModel):
    id: str
    capability_state: Literal['unknown']
    verification: Literal['unverified']
    input_modalities: None
    output_modalities: None
    tools: None
    streaming: None
    max_context_tokens: None
    max_output_tokens: None


class MemberCatalogResponse(InputModel):
    organization_id: UUID
    revision: int
    default_model: str
    models: list[UnknownModelResponse]


class DiscoveryResponse(InputModel):
    gateway_revision: int
    model_ids: list[str]
    capability_state: Literal['unknown']
    verification: Literal['unverified']


class PublicationResponse(InputModel):
    revision: int
    default_model: str
    models: list[str]


class AdminCatalogStatusResponse(InputModel):
    catalogue_revision: int
    default_model: str | None
    publication_state: Literal['CURRENT','UNPUBLISHED','STALE_GATEWAY']


class TextMessageBody(InputModel):
    role: Literal['system','user','assistant']
    content: Annotated[str,Field(strict=True,min_length=1,max_length=4096)]


class TextCompletionBody(InputModel):
    model: Annotated[str,Field(strict=True,pattern=r'^[a-z][a-z0-9_-]{0,63}$')]
    messages: Annotated[list[TextMessageBody],Field(min_length=1,max_length=16)]
    stream: Literal[True]
    max_output_tokens: Annotated[int,Field(strict=True,ge=1,le=2048)]=512

    @field_validator('stream',mode='before')
    @classmethod
    def strict_stream(cls,value):
        if value is not True:
            raise ValueError('Text streaming required.')
        return value


class DepartmentBody(InputModel):
    name: Annotated[str,Field(strict=True,min_length=1,max_length=120)]


class DepartmentResponse(InputModel):
    id: UUID
    name: str


class DepartmentListResponse(InputModel):
    departments: list[DepartmentResponse]


class MemberResponse(InputModel):
    id: UUID
    email: str
    display_name: str
    status: Literal['active','suspended']
    roles: list[str]
    departments: list[DepartmentResponse]


class MemberListResponse(InputModel):
    members: list[MemberResponse]


class MeAccountResponse(InputModel):
    id: UUID
    email: str
    display_name: str


class MeOrganizationResponse(InputModel):
    id: UUID
    display_name: str
    status: Literal['active']
    roles: list[str]
    departments: list[DepartmentResponse]


class MeResponse(InputModel):
    account: MeAccountResponse
    organizations: list[MeOrganizationResponse]


class ContractResponse(InputModel):
    contract_version: str
    schema_sha256: Annotated[str,Field(pattern=r'^[0-9a-f]{64}$')]


class AcceptBody(InputModel):
    invitation_id: UUID
    capability: Annotated[str,Field(strict=True,min_length=43,max_length=43,repr=False)]
    password: Annotated[str,Field(strict=True,min_length=15,max_length=1024,repr=False)]


class PreviewBody(InputModel):
    invitation_id: UUID
    capability: Annotated[str,Field(strict=True,min_length=43,max_length=43,repr=False)]


class InviteBody(InputModel):
    organization_id: UUID
    department_id: UUID
    email: Annotated[str,Field(strict=True,min_length=3,max_length=254)]
    name: Annotated[str,Field(strict=True,min_length=1,max_length=120)]


class ResetRequest(InputModel):
    email: Annotated[str,Field(strict=True,min_length=3,max_length=254)]


class ResetBody(InputModel):
    capability: Annotated[str,Field(strict=True,min_length=43,max_length=43,repr=False)]
    password: Annotated[str,Field(strict=True,min_length=15,max_length=1024,repr=False)]


class SessionResponse(InputModel):
    token_type: str='Bearer'
    access_token: str
    expires_at: str


class InvitationResponse(InputModel):
    invitation_id: UUID
    expires_at: str
    delivery_state: str
    delivery_channel: str


class EnrollmentResponse(InputModel):
    account_id: UUID
    organization_id: UUID
    membership_id: UUID
    department_id: UUID


class ResetAcceptedResponse(InputModel):
    status: str
    delivery_channel: str


class AccountFailure(Exception):
    def __init__(self,status: int,code: str,retry_seconds: int | None=None):
        self.status,self.code,self.retry_seconds=status,code,retry_seconds


def account_error(exc: AccountFailure):
    retry=exc.retry_seconds
    body=ErrorEnvelope(error=ErrorDetail(code=exc.code,message='Account authentication unavailable.',
        request_id=uuid4(),retryable=retry is not None,retry_after_seconds=retry,reset_at=None))
    headers={'Cache-Control':'no-store'}
    if exc.status==401:
        headers['WWW-Authenticate']='Bearer'
    if retry is not None:
        headers['Retry-After']=str(retry)
    return JSONResponse(status_code=exc.status,content=body.model_dump(mode='json'),headers=headers)


class RequestAdmission:
    """Finite process-local request admission, not a distributed production quota."""
    def __init__(self):
        self._lock=Lock()
        self._window=monotonic()
        self._count=0

    def admit(self):
        with self._lock:
            now=monotonic()
            if now-self._window>=1:
                self._window,self._count=now,0
            if self._count>=16:
                raise AccountFailure(429,'AUTHENTICATION_TEMPORARILY_BLOCKED',1)
            self._count+=1


class ReadySessionValidator:
    def __init__(self,sessions,readiness):
        self.sessions,self.readiness=sessions,readiness
    def validate(self,token):
        if self.sessions is None:
            return None
        if self.readiness is None or not self.readiness.check():
            raise InvitationUnavailable()
        identity = self.sessions.validate(token)
        return identity if genuine_identity(identity) else None


def create_account_app(*,sessions: SessionService | None=None,
        invitations: InvitationService | None=None,delivery: DeliveryCoordinator | None=None,
        bootstrap_reader: BootstrapReader | None=None,
        authorization_reader: AuthorizationReaderPort | None=None,
        readiness: ReadinessPort | None=None,
        gateway_configuration: GatewayConfiguration | None=None,
        gateway_catalog: GatewayCatalog | None=None,
        gateway_inference: GatewayInference | None=None,
        directory: DirectoryService | None=None,
        company_code: Callable[[str,UUID],str | None] | None=None) -> FastAPI:
    """All synchronous ports run in worker threads. Unconfigured composition denies.

    Caller owns separate account/enrollment/bootstrap pools, private local mailbox
    and explicit Fernet key/origin. This is not production SMTP or a legacy-runtime
    replacement. The exact account-aware readiness must pass before dispatch.
    """
    validator=ReadySessionValidator(sessions,readiness)
    app=create_app(token_validator=validator,bootstrap_reader=bootstrap_reader)
    admission=RequestAdmission()

    @app.exception_handler(AccountFailure)
    async def failure(request,exc):
        return account_error(exc)

    @app.exception_handler(GatewayConflict)
    async def gateway_conflict(request,exc):
        envelope=ErrorEnvelope(error=ErrorDetail(code='REVISION_CONFLICT',
            message='Gateway configuration revision changed.',request_id=uuid4(),
            retryable=False,retry_after_seconds=None,reset_at=None))
        return JSONResponse(status_code=409,content=envelope.model_dump(mode='json'),
                            headers={'Cache-Control':'no-store'})

    @app.exception_handler(GatewayManaged)
    async def gateway_managed(request,exc):
        # Deliberately outside the pinned error list: the code is the exception's own and the refusal is final.
        envelope=ErrorEnvelope(error=ErrorDetail(code=exc.code,
            message='The gateway key is managed by the platform.',request_id=uuid4(),
            retryable=False,retry_after_seconds=None,reset_at=None))
        return JSONResponse(status_code=403,content=envelope.model_dump(mode='json'),
                            headers={'Cache-Control':'no-store'})

    @app.exception_handler(GatewayOutsideCeiling)
    async def gateway_outside_ceiling(request,exc):
        # Outside the pinned error list like GatewayManaged: the administrator is told the platform ceiling is the reason.
        envelope=ErrorEnvelope(error=ErrorDetail(code=exc.code,
            message='A selected model is not allowed by the platform for this company.',request_id=uuid4(),
            retryable=False,retry_after_seconds=None,reset_at=None))
        return JSONResponse(status_code=409,content=envelope.model_dump(mode='json'),
                            headers={'Cache-Control':'no-store'})

    @app.exception_handler(DirectoryConflict)
    async def directory_conflict(request,exc):
        envelope=ErrorEnvelope(error=ErrorDetail(code='DEPARTMENT_EXISTS',
            message='A department with this name already exists.',request_id=uuid4(),
            retryable=False,retry_after_seconds=None,reset_at=None))
        return JSONResponse(status_code=409,content=envelope.model_dump(mode='json'),
                            headers={'Cache-Control':'no-store'})

    @app.exception_handler(DirectoryLastAdmin)
    async def directory_last_admin(request,exc):
        envelope=ErrorEnvelope(error=ErrorDetail(code='LAST_ADMIN',
            message='The last active administrator cannot be suspended.',request_id=uuid4(),
            retryable=False,retry_after_seconds=None,reset_at=None))
        return JSONResponse(status_code=409,content=envelope.model_dump(mode='json'),
                            headers={'Cache-Control':'no-store'})

    @app.middleware('http')
    async def private_account_transport(request: Request,call_next):
        if ((request.url.path.startswith('/forge/v1/accounts/') and request.method=='POST')
                or (request.url.path.startswith('/forge/v1/orgs/') and (
                    (request.url.path.endswith('/gateway') and request.method=='PUT')
                    or (request.url.path.endswith(('/departments','/suspend','/reactivate')) and request.method=='POST')
                    or (request.url.path.endswith(('/models/publish','/gateway/catalogue/refresh','/chat/completions')) and request.method=='POST')))):
            data=bytearray()
            async for chunk in request.stream():
                if len(data)+len(chunk)>(32768 if request.url.path.endswith(('/models/publish','/chat/completions')) else 8192):
                    return error_response(422,'INVALID_REQUEST',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer'})
                data.extend(chunk)
            # Starlette's cached request passes this bounded body to the inner app.
            request._body=bytes(data)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    def ready():
        admission.admit()
        try:
            if sessions is None or readiness is None or not readiness.check():
                raise ApiFailure(503,'SERVICE_UNAVAILABLE')
        except ApiFailure:
            raise
        except Exception:
            raise ApiFailure(503,'SERVICE_UNAVAILABLE') from None

    def invoke(operation,*args):
        try:
            return operation(*args)
        except (GatewayDenied,DirectoryDenied):
            raise ApiFailure(404,'NOT_FOUND') from None
        except DirectorySuspended:
            raise ApiFailure(403,'MEMBERSHIP_SUSPENDED') from None
        except (GatewayConflict,GatewayManaged,GatewayOutsideCeiling,DirectoryConflict,DirectoryLastAdmin):
            raise
        except (GatewayUnavailable,DirectoryUnavailable):
            raise ApiFailure(503,'SERVICE_UNAVAILABLE') from None
        except LoginThrottled as exc:
            raise AccountFailure(429,'AUTHENTICATION_TEMPORARILY_BLOCKED',exc.retry_seconds) from None
        except SessionDenied:
            raise AccountFailure(401,'UNAUTHENTICATED') from None
        except ExistingAccountAuthenticationRequired:
            raise AccountFailure(409,'EXISTING_ACCOUNT_AUTH_REQUIRED') from None
        except InvitationDenied:
            raise ApiFailure(404,'NOT_FOUND') from None
        except (InvitationUnavailable,PasswordWorkUnavailable):
            raise ApiFailure(503,'SERVICE_UNAVAILABLE') from None
        except ValueError:
            raise ApiFailure(422,'INVALID_REQUEST') from None
        except Exception:
            raise ApiFailure(503,'SERVICE_UNAVAILABLE') from None

    def token(request: Request):
        raw=request.headers.get('authorization','')
        scheme,separator,value=raw.partition(' ')
        if (len(request.headers.getlist('authorization'))!=1 or scheme.lower()!='bearer'
                or not separator or len(value)!=43 or any(c.isspace() for c in value)):
            raise AccountFailure(401,'UNAUTHENTICATED')
        ready()
        identity=invoke(sessions.validate,value)
        if not genuine_identity(identity):
            raise AccountFailure(401,'UNAUTHENTICATED')
        return value,identity

    def gateway_actor(organization_id: UUID,actor):
        if gateway_configuration is None or authorization_reader is None:
            raise ApiFailure(503,'SERVICE_UNAVAILABLE')
        snapshot=invoke(authorization_reader.read,actor[1],str(organization_id))
        if (type(snapshot) is not AuthorizationSnapshot or not valid_snapshot(snapshot)
                or snapshot.identity!=actor[1] or snapshot.organization_id!=organization_id
                or 'organization_admin' not in snapshot.roles):
            raise ApiFailure(404,'NOT_FOUND')
        # Snapshot is only fast-deny. The restricted store locks/revalidates the
        # actual session and current administrator inside the mutation transaction.
        return actor[0]

    @app.get('/forge/v1/orgs/{organization_id}/gateway',response_model=GatewayReadResponse,
              responses={status:{'model':ErrorEnvelope} for status in (401,404,422,503)},
              openapi_extra={'security':[{'ForgeBearer':[]}]})
    def get_gateway(organization_id: UUID,actor: Annotated[tuple,Depends(token)]):
        capability=gateway_actor(organization_id,actor)
        return invoke(gateway_configuration.read,capability,organization_id)

    @app.put('/forge/v1/orgs/{organization_id}/gateway',response_model=GatewayResponse,
              responses={status:{'model':ErrorEnvelope} for status in (401,404,409,422,503)},
              openapi_extra={'security':[{'ForgeBearer':[]}]})
    def put_gateway(organization_id: UUID,body: GatewayBody,actor: Annotated[tuple,Depends(token)]):
        capability=gateway_actor(organization_id,actor)
        if body.endpoint is None:
            return invoke(gateway_configuration.save,capability,organization_id,
                          body.expected_revision,body.api_key)
        # Deny before any key handling or storage; the service re-checks under its own policy.
        if body.endpoint not in gateway_configuration.allowed_endpoints:
            raise ApiFailure(422,'INVALID_REQUEST')
        return invoke(lambda: gateway_configuration.save(capability,organization_id,
            body.expected_revision,body.api_key,endpoint=body.endpoint))

    pin={}

    @app.get('/forge/v1/contract',response_model=ContractResponse)
    def contract_pin():
        # Public on purpose: it carries no tenant data, only the hash of the route contract
        # this very app serves, so a client can fail closed on drift before it logs in.
        if not pin:
            pin['value']={'contract_version':forge_contract.CONTRACT_VERSION,
                'schema_sha256':forge_contract.canonical_sha256(forge_contract.build(app))}
        return pin['value']

    def directory_port():
        if directory is None:
            raise ApiFailure(503,'SERVICE_UNAVAILABLE')
        return directory

    @app.get('/forge/v1/accounts/me',response_model=MeResponse,
              responses={status:{'model':ErrorEnvelope} for status in (401,403,404,503)},
              openapi_extra={'security':[{'ForgeBearer':[]}]})
    def accounts_me(actor: Annotated[tuple,Depends(token)]):
        # The organization context comes only from the live session, never from the caller.
        return invoke(directory_port().me,actor[0])

    @app.get('/forge/v1/orgs/{organization_id}/departments',response_model=DepartmentListResponse,
              responses={status:{'model':ErrorEnvelope} for status in (401,404,422,503)},
              openapi_extra={'security':[{'ForgeBearer':[]}]})
    def list_departments(organization_id: UUID,actor: Annotated[tuple,Depends(token)]):
        return {'departments':invoke(directory_port().departments,actor[0],organization_id)}

    @app.post('/forge/v1/orgs/{organization_id}/departments',status_code=201,response_model=DepartmentResponse,
              responses={status:{'model':ErrorEnvelope} for status in (401,404,409,422,503)},
              openapi_extra={'security':[{'ForgeBearer':[]}]})
    def create_department(organization_id: UUID,body: DepartmentBody,actor: Annotated[tuple,Depends(token)]):
        return invoke(directory_port().create_department,actor[0],organization_id,body.name)

    @app.get('/forge/v1/orgs/{organization_id}/members',response_model=MemberListResponse,
              responses={status:{'model':ErrorEnvelope} for status in (401,404,422,503)},
              openapi_extra={'security':[{'ForgeBearer':[]}]})
    def list_members(organization_id: UUID,actor: Annotated[tuple,Depends(token)]):
        return {'members':invoke(directory_port().members,actor[0],organization_id)}

    @app.post('/forge/v1/orgs/{organization_id}/members/{member_id}/suspend',response_model=MemberResponse,
              responses={status:{'model':ErrorEnvelope} for status in (401,404,409,422,503)},
              openapi_extra={'security':[{'ForgeBearer':[]}]})
    def suspend_member(organization_id: UUID,member_id: UUID,actor: Annotated[tuple,Depends(token)]):
        return invoke(directory_port().suspend_member,actor[0],organization_id,member_id)

    @app.post('/forge/v1/orgs/{organization_id}/members/{member_id}/reactivate',response_model=MemberResponse,
              responses={status:{'model':ErrorEnvelope} for status in (401,404,422,503)},
              openapi_extra={'security':[{'ForgeBearer':[]}]})
    def reactivate_member(organization_id: UUID,member_id: UUID,actor: Annotated[tuple,Depends(token)]):
        return invoke(directory_port().reactivate_member,actor[0],organization_id,member_id)

    def catalog_actor(organization_id,actor,*,admin=False):
        if gateway_catalog is None:
            raise ApiFailure(503,'SERVICE_UNAVAILABLE')
        if admin:
            if authorization_reader is None:
                raise ApiFailure(503,'SERVICE_UNAVAILABLE')
            snapshot=invoke(authorization_reader.read,actor[1],str(organization_id))
            if (type(snapshot) is not AuthorizationSnapshot or not valid_snapshot(snapshot)
                    or snapshot.identity!=actor[1] or snapshot.organization_id!=organization_id
                    or 'organization_admin' not in snapshot.roles):
                raise ApiFailure(404,'NOT_FOUND')
        return actor[0]

    @app.get('/forge/v1/orgs/{organization_id}/gateway/catalogue/status',response_model=AdminCatalogStatusResponse,
              responses={status:{'model':ErrorEnvelope} for status in (401,404,422,503)},
              openapi_extra={'security':[{'ForgeBearer':[]}]})
    def admin_catalog_status(organization_id: UUID,actor: Annotated[tuple,Depends(token)]):
        capability=catalog_actor(organization_id,actor,admin=True)
        return invoke(gateway_catalog.admin_status,capability,organization_id)

    @app.post('/forge/v1/orgs/{organization_id}/gateway/catalogue/refresh',response_model=DiscoveryResponse,
              responses={status:{'model':ErrorEnvelope} for status in (401,404,409,422,503)},
              openapi_extra={'security':[{'ForgeBearer':[]}]})
    async def refresh_catalog(organization_id: UUID,actor: Annotated[tuple,Depends(token)]):
        from functools import partial
        from anyio.to_thread import run_sync
        capability=await run_sync(partial(catalog_actor,organization_id,actor,admin=True),abandon_on_cancel=False)
        try:
            return await gateway_catalog.refresh_async(capability,organization_id)
        except GatewayDenied:
            raise ApiFailure(404,'NOT_FOUND') from None
        except GatewayConflict:
            raise
        except Exception:
            raise ApiFailure(503,'SERVICE_UNAVAILABLE') from None

    @app.post('/forge/v1/orgs/{organization_id}/models/publish',response_model=PublicationResponse,
              responses={status:{'model':ErrorEnvelope} for status in (401,404,409,422,503)},
              openapi_extra={'security':[{'ForgeBearer':[]}]})
    def publish_catalog(organization_id: UUID,body: CatalogPublishBody,actor: Annotated[tuple,Depends(token)]):
        capability=catalog_actor(organization_id,actor,admin=True)
        return invoke(gateway_catalog.publish,capability,organization_id,
            body.operation_id,body.expected_catalogue_revision,body.expected_gateway_revision,
            body.aliases,body.default_alias)

    @app.get('/forge/v1/orgs/{organization_id}/models',response_model=MemberCatalogResponse,
              responses={status:{'model':ErrorEnvelope} for status in (401,404,422,503)},
              openapi_extra={'security':[{'ForgeBearer':[]}]})
    def read_catalog(organization_id: UUID,actor: Annotated[tuple,Depends(token)]):
        capability=catalog_actor(organization_id,actor)
        return invoke(gateway_catalog.read,capability,organization_id)

    @app.post('/forge/v1/orgs/{organization_id}/chat/completions',
              responses={200:{'content':{'text/event-stream':{}}},
                         **{status:{'model':ErrorEnvelope} for status in (401,404,422,503)}},
              openapi_extra={'security':[{'ForgeBearer':[]}]})
    async def text_completion(organization_id: UUID,body: TextCompletionBody,
                              request: Request,actor: Annotated[tuple,Depends(token)]):
        if gateway_inference is None:
            raise ApiFailure(503,'SERVICE_UNAVAILABLE')
        try:
            text=TextRequest(body.model,tuple((item.role,item.content) for item in body.messages),
                             body.max_output_tokens)
            prepared=await gateway_inference.prepare(actor[0],organization_id,text)
        except GatewayDenied:
            raise ApiFailure(404,'NOT_FOUND') from None
        except ValueError:
            raise ApiFailure(422,'INVALID_REQUEST') from None
        except Exception:
            raise ApiFailure(503,'SERVICE_UNAVAILABLE') from None
        return StreamingResponse(gateway_inference.stream(prepared,disconnected=request.is_disconnected),
                                 media_type='text/event-stream')

    @app.post('/forge/v1/accounts/login',response_model=SessionResponse,
              responses={status:{'model':ErrorEnvelope} for status in (401,422,429,503)})
    def login(body: LoginBody,_: Annotated[None,Depends(ready)]):
        result=invoke(sessions.login,body.email,body.password)
        if type(result) is not AccountSession:
            raise ApiFailure(503,'SERVICE_UNAVAILABLE')
        try:
            from forge.invitations import capability_digest
            capability_digest(result.capability)
            return SessionResponse(access_token=result.capability,expires_at=result.expires_at.isoformat())
        except Exception:
            raise ApiFailure(503,'SERVICE_UNAVAILABLE') from None

    @app.post('/forge/v1/accounts/logout',status_code=204,openapi_extra={'security':[{'ForgeBearer':[]}]})
    def logout(actor: Annotated[tuple,Depends(token)]):
        if not invoke(sessions.logout,actor[0]):
            raise AccountFailure(401,'UNAUTHENTICATED')

    @app.post('/forge/v1/accounts/disable',status_code=204,openapi_extra={'security':[{'ForgeBearer':[]}]})
    def disable(actor: Annotated[tuple,Depends(token)]):
        if not invoke(sessions.disable,actor[0]):
            raise AccountFailure(401,'UNAUTHENTICATED')

    def code_hint(token,organization_id):
        """The company's public code for the mailed link's ``c=`` hint, so the join page is branded. Never blocks an invitation."""
        if company_code is None:
            return None
        try:
            code=company_code(token,organization_id)
        except Exception:
            return None
        return code if type(code) is str and COMPANY_CODE.fullmatch(code) else None

    @app.post('/forge/v1/accounts/invitations',status_code=201,response_model=InvitationResponse,openapi_extra={'security':[{'ForgeBearer':[]}]})
    def invite(body: InviteBody,actor: Annotated[tuple,Depends(token)]):
        if invitations is None or delivery is None or authorization_reader is None:
            raise ApiFailure(503,'SERVICE_UNAVAILABLE')
        snapshot=invoke(authorization_reader.read,actor[1],str(body.organization_id))
        if (type(snapshot) is not AuthorizationSnapshot or not valid_snapshot(snapshot)
                or snapshot.identity!=actor[1] or snapshot.organization_id!=body.organization_id
                or 'organization_admin' not in snapshot.roles):
            raise ApiFailure(404,'NOT_FOUND')
        request=InvitationRequest(body.organization_id,snapshot.membership_id,body.department_id,body.email,body.name)
        issued=invoke(invitations.issue,actor[1],request)
        message=invoke(delivery.queue_invitation,issued,request,code_hint(actor[0],body.organization_id))
        state=invoke(delivery.dispatch,message)
        return invoke(lambda: {'invitation_id':str(issued.invitation_id),'expires_at':issued.expires_at.isoformat(),
                'delivery_state':state.value,'delivery_channel':delivery.channel})

    @app.post('/forge/v1/accounts/invitations/preview',include_in_schema=False)
    def preview(body: PreviewBody,_: Annotated[None,Depends(ready)]):
        # Hidden and outside the pinned contract on purpose: the pinned accept response cannot carry the address. The holder of the
        # private link learns who the invitation is for; every unusable invitation is the same 404.
        if invitations is None:
            raise ApiFailure(503,'SERVICE_UNAVAILABLE')
        result=invoke(invitations.preview,body.invitation_id,body.capability)
        return JSONResponse({'account_email':result.account_email,'display_name':result.display_name})

    @app.post('/forge/v1/accounts/invitations/accept',status_code=201,response_model=EnrollmentResponse)
    def accept(body: AcceptBody,_: Annotated[None,Depends(ready)]):
        if invitations is None:
            raise ApiFailure(503,'SERVICE_UNAVAILABLE')
        result=invoke(invitations.accept,body.invitation_id,body.capability,body.password)
        return invoke(lambda: {'account_id':str(result.account_id),'organization_id':str(result.organization_id),
                'membership_id':str(result.membership_id),'department_id':str(result.department_id)})

    @app.post('/forge/v1/accounts/password-reset/request',status_code=202,response_model=ResetAcceptedResponse)
    def request_reset(body: ResetRequest,_: Annotated[None,Depends(ready)]):
        if delivery is None:
            raise ApiFailure(503,'SERVICE_UNAVAILABLE')
        intent=invoke(sessions.request_reset,body.email)
        if intent is not None:
            message=invoke(delivery.queue_reset,intent)
            invoke(delivery.dispatch,message)
        # Same output for unknown, disabled, throttled and known accounts.
        return {'status':'accepted','delivery_channel':invoke(lambda: delivery.channel)}

    @app.post('/forge/v1/accounts/password-reset/consume',status_code=204)
    def consume_reset(body: ResetBody,_: Annotated[None,Depends(ready)]):
        if not invoke(sessions.reset,body.capability,body.password):
            raise ApiFailure(404,'NOT_FOUND')

    return app

"""Invitation issuance/revocation revalidate database authority, never role claims."""
from uuid import UUID
import re

from forge.accounts import canonical_email, display_name
from forge.account_store import EnrollmentConnection
from forge.invitations import InvitationRequest, InvitationUnavailable, validate_actor


class PostgresInvitationStore:
    def __init__(self, pool, *, acquisition_timeout=1.0):
        self.connection = EnrollmentConnection(pool, acquisition_timeout=acquisition_timeout)

    def issue(self, identity, request, invitation_id, membership_id, digest):
        if type(request) is not InvitationRequest:
            raise ValueError("Invalid invitation input.")
        validate_actor(identity, request.organization_id, request.administrator_membership_id,
                       request.department_id, invitation_id, membership_id)
        if (canonical_email(request.email)!=request.email or display_name(request.name)!=request.name
                or type(digest) is not str or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or type(request.lifetime_seconds) is not int
                or not 60<=request.lifetime_seconds<=604800):
            raise ValueError("Invalid invitation input.")
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT forge.issue_account_invitation(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (request.organization_id,request.administrator_membership_id,identity.provider,
                 identity.issuer,identity.subject,request.department_id,invitation_id,membership_id,
                 request.email,request.name,digest,request.lifetime_seconds))
            row = cursor.fetchone()
            if row is None or row[0] is None:
                raise InvitationUnavailable()
            return row[0]

    def revoke(self, identity, organization_id, administrator_membership_id, invitation_id):
        validate_actor(identity, organization_id, administrator_membership_id, invitation_id)
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT forge.revoke_account_invitation(%s,%s,%s,%s,%s,%s)",
                (organization_id,administrator_membership_id,identity.provider,identity.issuer,
                 identity.subject,invitation_id))
            row = cursor.fetchone()
            if row != (True,):
                raise InvitationUnavailable()
            return True

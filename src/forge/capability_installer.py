"""The per-company installer configuration: what the desktop client needs before its first sign-in, from the control plane it will talk to.

A member downloads it from the portal (``GET /forge/v1/capabilities/installer-config``, a member session). It holds the company code, the
control plane origin and the policy key set to pin (active and retired keys); a later rotation is followed with the signed statements of
``GET /forge/v1/capabilities/pinning`` (see ``forge.capability_rotation``). It contains no secret: the keys are public.
"""
from forge.capability_model import CapabilityNotFound
from forge.gateway_origins import canonical_origin
from forge.invitation_delivery import COMPANY_CODE

INSTALLER_SCHEMA = 'forge.installer-config.v1'


class InstallerConfig:
    def __init__(self, policy, origin, company_code):
        if type(origin) is not str:
            raise ValueError('The control plane origin is invalid.')
        self._policy, self._origin, self._company_code = policy, canonical_origin(origin, dev=True), company_code

    def company_code(self, token, org):
        """The member's company code (a valid slug), else not found: it names the installer download as well as the configuration."""
        code = self._company_code(token, org)
        if type(code) is not str or not COMPANY_CODE.fullmatch(code):
            raise CapabilityNotFound()
        return code

    def document(self, token, org):
        keys = self._policy.keys()  # no signing key: unavailable, like the key set itself
        code = self.company_code(token, org)
        return {'schema': INSTALLER_SCHEMA, 'company_code': code, 'control_plane_origin': self._origin, 'policy_keys': keys}

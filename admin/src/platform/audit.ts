const LABELS: Record<string, string> = {
  "company.created": "Company created",
  "company.suspended": "Company suspended",
  "company.reactivated": "Company reactivated",
  "company.branding_saved": "Branding saved",
  "company.gateway_assigned": "Gateway keys assigned",
  "company.model_access_set": "Model access set",
  "gateway_key.created": "Gateway key added",
  "gateway_key.rotated": "Gateway key rotated",
  "gateway_key.status_changed": "Gateway key enabled or disabled",
  "model_price.set": "Model price set",
  "owner.mfa_enrolled": "Second factor enrolled",
  "owner.mfa_recovery_used": "Recovery code used",
};

/** The audit actions the platform records, as sentences; an action this console does not know is shown verbatim. */
export const describeAction = (action: string): string => LABELS[action] ?? action;
export const KNOWN_ACTIONS: readonly string[] = Object.keys(LABELS);

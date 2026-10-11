// Must stay byte-identical to ADMIN_CSP in src/forge/admin_mount.py (see unit/csp.spec.ts).
export const ADMIN_CSP =
  "default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'";

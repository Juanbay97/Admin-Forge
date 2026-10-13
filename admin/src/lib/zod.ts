// zod compiles validators with `new Function` unless told not to; under `script-src 'self'` the probe itself is reported as a
// securitypolicyviolation. Every module that parses with zod imports `z` from here so the setting is applied first.
import { config, z } from "zod";

config({ jitless: true });

export { z };
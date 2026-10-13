-- A company administrator no longer stores a gateway key: the key is the platform's (0032) and the administrator keeps
-- only the read-only status (gateway_status, 0033). The member-route service pool therefore loses EXECUTE on both
-- gateway_save overloads, so even a compromised application process cannot write a legacy key. The legacy table and the
-- functions stay (the retained demo profile and the legacy fallback of the router read them); nothing is deleted.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
REVOKE ALL ON FUNCTION forge.gateway_save(text,uuid,bigint,uuid,text),forge.gateway_save(text,uuid,bigint,uuid,text,text)
 FROM forge_gateway_service;
COMMIT;

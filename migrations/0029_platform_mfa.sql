-- Mandatory TOTP for the platform owner. Additive; the only change to an existing object is that
-- platform_lock_owner (0028) now also requires a verified second factor for the very session that calls it.
-- * platform_totp: the shared secret exists only sealed (the application's Fernet key), plus the replay guard (the last
--   accepted 30 s step) and a durable attempt budget that is spent BEFORE a code is checked, so parallel guesses cannot
--   outrun it (the pattern of account_begin_login).
-- * platform_recovery_codes: ten single-use codes, stored only as SHA-256 digests.
-- * platform_mfa_sessions: one row per account session that passed the factor; it disappears with the session.
-- Everything stays owned by forge_platform_authority; the service role still holds no table privilege.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;

CREATE TABLE forge.platform_totp (
 account_id uuid PRIMARY KEY REFERENCES forge.platform_roles(account_id),
 sealed_secret text NOT NULL CHECK(length(sealed_secret) BETWEEN 80 AND 400),
 state text NOT NULL CHECK(state IN ('pending','active')),
 last_step bigint NOT NULL DEFAULT 0 CHECK(last_step>=0),
 failed_attempts integer NOT NULL DEFAULT 0 CHECK(failed_attempts BETWEEN 0 AND 5),
 attempt_window timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 activated_at timestamptz,
 CHECK((state='active')=(activated_at IS NOT NULL))
);
CREATE TABLE forge.platform_recovery_codes (
 account_id uuid NOT NULL REFERENCES forge.platform_roles(account_id),
 code_hash text NOT NULL CHECK(code_hash ~ '^[0-9a-f]{64}$'),
 used_at timestamptz,
 PRIMARY KEY(account_id,code_hash)
);
CREATE TABLE forge.platform_mfa_sessions (
 capability_hash text PRIMARY KEY REFERENCES forge.account_sessions(capability_hash) ON DELETE CASCADE,
 account_id uuid NOT NULL REFERENCES forge.platform_roles(account_id),
 verified_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['platform_totp','platform_recovery_codes','platform_mfa_sessions'] LOOP
  EXECUTE format('ALTER TABLE forge.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE forge.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON forge.%I FROM PUBLIC,forge_runtime,forge_enrollment,forge_account_service,forge_gateway_service,forge_branding_service,forge_platform_service',t);
  EXECUTE format('CREATE POLICY platform_scope ON forge.%I TO forge_platform_authority USING(true) WITH CHECK(true)',t);
 END LOOP;
END $$;
GRANT SELECT,INSERT,UPDATE ON forge.platform_totp TO forge_platform_authority;
GRANT SELECT,INSERT,UPDATE,DELETE ON forge.platform_recovery_codes TO forge_platform_authority;
GRANT SELECT,INSERT,UPDATE ON forge.platform_mfa_sessions TO forge_platform_authority;
RESET ROLE;

GRANT CREATE ON SCHEMA forge TO forge_platform_authority;
SET LOCAL ROLE forge_platform_authority;

-- Internal: a live account session of a platform owner, with NO second-factor requirement (the factor's own
-- functions need it). Anyone else, including a company administrator or a viewer, gets PLATFORM_DENIED.
CREATE FUNCTION forge.platform_session_owner(digest text) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid;
BEGIN
 account:=forge.account_validate_session(digest);
 IF account IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_DENIED';
 END IF;
 PERFORM 1 FROM forge.platform_roles r WHERE r.account_id=account AND r.role='platform_owner';
 IF NOT FOUND THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_DENIED';
 END IF;
 RETURN account;
END $$;

-- Replaces the 0028 version (same signature, owner and grants): the session must also have passed the factor, and a
-- change (fresh=true) must have passed it within the last 30 minutes.
CREATE OR REPLACE FUNCTION forge.platform_lock_owner(digest text,fresh boolean) RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid;
BEGIN
 account:=forge.platform_session_owner(digest);
 IF fresh IS NULL THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_DENIED';
 END IF;
 PERFORM 1 FROM forge.platform_mfa_sessions m
  JOIN forge.platform_totp t ON t.account_id=m.account_id AND t.state='active'
  WHERE m.capability_hash=digest AND m.account_id=account
   AND (NOT fresh OR m.verified_at>clock_timestamp()-interval '30 minutes');
 IF NOT FOUND THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='MFA_REQUIRED';
 END IF;
 RETURN account;
END $$;

-- Callable with a password-only session: where this session stands.
CREATE FUNCTION forge.platform_mfa_status(digest text) RETURNS TABLE(state text,verified boolean,fresh boolean)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid; have text; seen timestamptz;
BEGIN
 account:=forge.account_validate_session(digest);
 IF account IS NULL OR NOT EXISTS(SELECT 1 FROM forge.platform_roles r WHERE r.account_id=account) THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_DENIED';
 END IF;
 SELECT t.state INTO have FROM forge.platform_totp t WHERE t.account_id=account;
 IF NOT FOUND THEN have:='none'; END IF;
 SELECT m.verified_at INTO seen FROM forge.platform_mfa_sessions m WHERE m.capability_hash=digest AND m.account_id=account;
 RETURN QUERY SELECT have,seen IS NOT NULL AND have='active',
  coalesce(have='active' AND seen>clock_timestamp()-interval '30 minutes',false);
END $$;

-- Start (or restart, while still pending) the enrollment: the sealed secret and ten recovery-code digests. An active
-- factor is never replaced through the API (the operator resets it), so a stolen password session cannot swap it.
CREATE FUNCTION forge.platform_mfa_enroll(digest text,sealed text,hashes text[]) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid; have text;
BEGIN
 account:=forge.platform_session_owner(digest);
 IF sealed IS NULL OR length(sealed) NOT BETWEEN 80 AND 400 OR hashes IS NULL OR cardinality(hashes)<>10
  OR EXISTS(SELECT 1 FROM unnest(hashes) h WHERE h IS NULL OR h !~ '^[0-9a-f]{64}$')
  OR (SELECT count(DISTINCT h) FROM unnest(hashes) h)<>10 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 SELECT t.state INTO have FROM forge.platform_totp t WHERE t.account_id=account FOR UPDATE;
 IF FOUND AND have='active' THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='MFA_ENROLLED';
 END IF;
 INSERT INTO forge.platform_totp(account_id,sealed_secret,state) VALUES(account,sealed,'pending')
  ON CONFLICT(account_id) DO UPDATE SET sealed_secret=excluded.sealed_secret,state='pending',last_step=0,
   failed_attempts=0,attempt_window=NULL,created_at=clock_timestamp();
 DELETE FROM forge.platform_recovery_codes c WHERE c.account_id=account;
 INSERT INTO forge.platform_recovery_codes(account_id,code_hash) SELECT account,h FROM unnest(hashes) h;
 RETURN true;
END $$;

-- Spend one attempt BEFORE any code is checked and hand back what the application needs to check it. Five attempts per
-- 15 minutes; the counter is only reset by a success or when the window has passed.
CREATE FUNCTION forge.platform_mfa_begin(digest text) RETURNS TABLE(state text,sealed text,last_step bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid; rec record;
BEGIN
 account:=forge.platform_session_owner(digest);
 SELECT * INTO rec FROM forge.platform_totp t WHERE t.account_id=account FOR UPDATE;
 IF NOT FOUND THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='MFA_INVALID';
 END IF;
 IF rec.attempt_window IS NULL OR rec.attempt_window<=clock_timestamp()-interval '15 minutes' THEN
  UPDATE forge.platform_totp t SET failed_attempts=0,attempt_window=clock_timestamp() WHERE t.account_id=account;
  rec.failed_attempts:=0;
 END IF;
 IF rec.failed_attempts>=5 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='MFA_LOCKED';
 END IF;
 UPDATE forge.platform_totp t SET failed_attempts=t.failed_attempts+1 WHERE t.account_id=account;
 RETURN QUERY SELECT rec.state,rec.sealed_secret,rec.last_step;
END $$;

-- Accept one 30 s step: strictly newer than the last accepted one (the replay guard, per account, across sessions) and
-- within one step of the database clock. The first success activates a pending factor and is audited.
CREATE FUNCTION forge.platform_mfa_confirm(digest text,step bigint) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid; rec record;
BEGIN
 account:=forge.platform_session_owner(digest);
 SELECT * INTO rec FROM forge.platform_totp t WHERE t.account_id=account FOR UPDATE;
 IF NOT FOUND OR step IS NULL OR step<=rec.last_step
  OR abs(step-floor(extract(epoch FROM clock_timestamp())/30)::bigint)>1 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='MFA_INVALID';
 END IF;
 UPDATE forge.platform_totp t SET last_step=step,failed_attempts=0,attempt_window=NULL,state='active',
  activated_at=coalesce(t.activated_at,clock_timestamp()) WHERE t.account_id=account;
 INSERT INTO forge.platform_mfa_sessions(capability_hash,account_id) VALUES(digest,account)
  ON CONFLICT(capability_hash) DO UPDATE SET verified_at=clock_timestamp();
 IF rec.state='pending' THEN
  PERFORM forge.platform_audit_write(account,'owner.mfa_enrolled',NULL);
 END IF;
 RETURN true;
END $$;

-- Spend one recovery code (its digest) and verify this session. Only an active factor has usable codes.
CREATE FUNCTION forge.platform_mfa_recover(digest text,hashed text) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid;
BEGIN
 account:=forge.platform_session_owner(digest);
 IF hashed IS NULL OR hashed !~ '^[0-9a-f]{64}$' THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='MFA_INVALID';
 END IF;
 PERFORM 1 FROM forge.platform_totp t WHERE t.account_id=account AND t.state='active' FOR UPDATE;
 IF NOT FOUND THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='MFA_INVALID';
 END IF;
 UPDATE forge.platform_recovery_codes c SET used_at=clock_timestamp()
  WHERE c.account_id=account AND c.code_hash=hashed AND c.used_at IS NULL;
 IF NOT FOUND THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='MFA_INVALID';
 END IF;
 UPDATE forge.platform_totp t SET failed_attempts=0,attempt_window=NULL WHERE t.account_id=account;
 INSERT INTO forge.platform_mfa_sessions(capability_hash,account_id) VALUES(digest,account)
  ON CONFLICT(capability_hash) DO UPDATE SET verified_at=clock_timestamp();
 PERFORM forge.platform_audit_write(account,'owner.mfa_recovery_used',NULL);
 RETURN true;
END $$;

RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_platform_authority;
REVOKE ALL ON FUNCTION forge.platform_session_owner(text),forge.platform_mfa_status(text),
 forge.platform_mfa_enroll(text,text,text[]),forge.platform_mfa_begin(text),forge.platform_mfa_confirm(text,bigint),
 forge.platform_mfa_recover(text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.platform_mfa_status(text),forge.platform_mfa_enroll(text,text,text[]),
 forge.platform_mfa_begin(text),forge.platform_mfa_confirm(text,bigint),forge.platform_mfa_recover(text,text)
 TO forge_platform_service;
COMMIT;

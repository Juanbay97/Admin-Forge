-- Member own usage. Additive and forward-only.
-- * ``usage_member_me`` is a function of the existing directory authority: it re-validates the live session, requires an ACTIVE
--   membership of an ACTIVE company and then sums only that membership's rows of the daily rollup over a bounded UTC range (at most
--   366 days). The member is derived from the session inside the function, never taken from an argument, so nobody can read another
--   person's counters through it. A stranger, another company's person, a suspended member, an inactive company and a stale
--   session are the same ``DIRECTORY_DENIED``.
-- * It returns counters and integer micro-USD costs only; a range without usage is one row of zeros.
-- No login role gains a table privilege; the function is executable by the gateway service pool only.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
GRANT CREATE ON SCHEMA forge TO forge_directory_authority;
SET LOCAL ROLE forge_directory_authority;
CREATE FUNCTION forge.usage_member_me(digest text,org uuid,first_day date,last_day date)
RETURNS TABLE(requests bigint,prompt_tokens bigint,completion_tokens bigint,estimated_requests bigint,error_requests bigint,
 cost_micros bigint,unpriced_requests bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE account uuid; member uuid;
BEGIN
 account:=forge.directory_account(digest);
 SELECT m.id INTO member FROM forge.memberships m JOIN forge.organizations o ON o.id=m.organization_id AND o.active
  WHERE org IS NOT NULL AND m.organization_id=org AND m.identity_id=account AND m.status='active';
 IF member IS NULL THEN RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='DIRECTORY_DENIED'; END IF;
 IF first_day IS NULL OR last_day IS NULL OR first_day>last_day OR last_day-first_day>365 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='DIRECTORY_INVALID';
 END IF;
 -- The existing company policy opens the company's rows once the context is pinned; the filter narrows them to the own membership.
 PERFORM set_config('forge.directory_org',org::text,true);
 RETURN QUERY SELECT coalesce(sum(d.requests),0)::bigint,coalesce(sum(d.prompt_tokens),0)::bigint,
   coalesce(sum(d.completion_tokens),0)::bigint,coalesce(sum(d.estimated_requests),0)::bigint,
   coalesce(sum(d.error_requests),0)::bigint,coalesce(sum(d.cost_micros),0)::bigint,coalesce(sum(d.unpriced_requests),0)::bigint
  FROM forge.usage_daily d WHERE d.organization_id=org AND d.membership_id=member AND d.day BETWEEN first_day AND last_day;
END $$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_directory_authority;
REVOKE ALL ON FUNCTION forge.usage_member_me(text,uuid,date,date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.usage_member_me(text,uuid,date,date) TO forge_gateway_service;
COMMIT;

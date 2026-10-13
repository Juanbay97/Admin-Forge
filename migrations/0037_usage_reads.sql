-- Usage reads. Additive and forward-only.
-- * Platform reports (fresh not required, verified owner session required): usage per company, per upstream model and in total over
--   a bounded UTC date range (at most 366 days) with keyset pagination. They read only the daily rollup, so they carry counters
--   and integer micro-USD costs (plus the number of unpriced requests), never content.
-- * The company per-person report is a function of the existing directory authority: it re-validates the live session and the
--   organization administrator (directory_admin) and then reads only that company's rollup rows with the member's name and email,
--   including suspended members (their history stays visible). Another company, a member or a stale session is denied.
-- No login role gains a table privilege; the recording pool still cannot read.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
SET LOCAL ROLE forge_migrator;
CREATE POLICY platform_scope ON forge.usage_daily FOR SELECT TO forge_platform_authority USING(true);
CREATE POLICY directory_org_usage ON forge.usage_daily FOR SELECT TO forge_directory_authority
 USING(organization_id=forge.enrollment_uuid('forge.directory_org'));
GRANT SELECT ON forge.usage_daily TO forge_platform_authority,forge_directory_authority;
RESET ROLE;

GRANT CREATE ON SCHEMA forge TO forge_platform_authority;
SET LOCAL ROLE forge_platform_authority;
-- Internal: a bounded, ordered range and page, or PLATFORM_INVALID.
CREATE FUNCTION forge.platform_usage_range(first_day date,last_day date,page integer) RETURNS void
LANGUAGE plpgsql IMMUTABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 IF first_day IS NULL OR last_day IS NULL OR page IS NULL OR first_day>last_day OR last_day-first_day>365
  OR page NOT BETWEEN 1 AND 100 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
END $$;

CREATE FUNCTION forge.platform_usage_by_company(digest text,first_day date,last_day date,after_org uuid,page integer)
RETURNS TABLE(organization_id uuid,slug text,display_name text,requests bigint,prompt_tokens bigint,completion_tokens bigint,
 estimated_requests bigint,error_requests bigint,cost_micros bigint,unpriced_requests bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 PERFORM forge.platform_usage_range(first_day,last_day,page);
 PERFORM set_config('forge.platform_list','1',true);
 RETURN QUERY SELECT o.id,o.slug,o.display_name,t.requests,t.prompt_tokens,t.completion_tokens,t.estimated_requests,
   t.error_requests,t.cost_micros,t.unpriced_requests
  FROM (SELECT d.organization_id AS org,sum(d.requests)::bigint AS requests,sum(d.prompt_tokens)::bigint AS prompt_tokens,
    sum(d.completion_tokens)::bigint AS completion_tokens,sum(d.estimated_requests)::bigint AS estimated_requests,
    sum(d.error_requests)::bigint AS error_requests,sum(d.cost_micros)::bigint AS cost_micros,
    sum(d.unpriced_requests)::bigint AS unpriced_requests
   FROM forge.usage_daily d WHERE d.day BETWEEN first_day AND last_day GROUP BY d.organization_id) t
  JOIN forge.organizations o ON o.id=t.org WHERE after_org IS NULL OR o.id>after_org ORDER BY o.id LIMIT page;
 PERFORM set_config('forge.platform_list','',true);
END $$;

CREATE FUNCTION forge.platform_usage_by_model(digest text,first_day date,last_day date,after_model text,page integer)
RETURNS TABLE(upstream_id text,requests bigint,prompt_tokens bigint,completion_tokens bigint,estimated_requests bigint,
 error_requests bigint,cost_micros bigint,unpriced_requests bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 PERFORM forge.platform_usage_range(first_day,last_day,page);
 IF after_model IS NOT NULL AND length(after_model)>255 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PLATFORM_INVALID';
 END IF;
 RETURN QUERY SELECT d.upstream_id,sum(d.requests)::bigint,sum(d.prompt_tokens)::bigint,sum(d.completion_tokens)::bigint,
   sum(d.estimated_requests)::bigint,sum(d.error_requests)::bigint,sum(d.cost_micros)::bigint,sum(d.unpriced_requests)::bigint
  FROM forge.usage_daily d WHERE d.day BETWEEN first_day AND last_day AND (after_model IS NULL OR d.upstream_id>after_model)
  GROUP BY d.upstream_id ORDER BY d.upstream_id LIMIT page;
END $$;

CREATE FUNCTION forge.platform_usage_totals(digest text,first_day date,last_day date)
RETURNS TABLE(companies bigint,requests bigint,prompt_tokens bigint,completion_tokens bigint,estimated_requests bigint,
 error_requests bigint,cost_micros bigint,unpriced_requests bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 PERFORM forge.platform_usage_range(first_day,last_day,1);
 RETURN QUERY SELECT count(DISTINCT d.organization_id),coalesce(sum(d.requests),0)::bigint,coalesce(sum(d.prompt_tokens),0)::bigint,
   coalesce(sum(d.completion_tokens),0)::bigint,coalesce(sum(d.estimated_requests),0)::bigint,
   coalesce(sum(d.error_requests),0)::bigint,coalesce(sum(d.cost_micros),0)::bigint,coalesce(sum(d.unpriced_requests),0)::bigint
  FROM forge.usage_daily d WHERE d.day BETWEEN first_day AND last_day;
END $$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_platform_authority;
REVOKE ALL ON FUNCTION forge.platform_usage_range(date,date,integer),forge.platform_usage_by_company(text,date,date,uuid,integer),
 forge.platform_usage_by_model(text,date,date,text,integer),forge.platform_usage_totals(text,date,date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.platform_usage_by_company(text,date,date,uuid,integer),
 forge.platform_usage_by_model(text,date,date,text,integer),forge.platform_usage_totals(text,date,date) TO forge_platform_service;

GRANT CREATE ON SCHEMA forge TO forge_directory_authority;
SET LOCAL ROLE forge_directory_authority;
CREATE FUNCTION forge.usage_company_members(digest text,org uuid,first_day date,last_day date,after_member uuid,page integer)
RETURNS TABLE(member_id uuid,member_email text,member_name text,member_state text,requests bigint,prompt_tokens bigint,
 completion_tokens bigint,estimated_requests bigint,error_requests bigint,cost_micros bigint,unpriced_requests bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.directory_admin(digest,org);
 IF first_day IS NULL OR last_day IS NULL OR page IS NULL OR first_day>last_day OR last_day-first_day>365
  OR page NOT BETWEEN 1 AND 100 THEN
  RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='DIRECTORY_INVALID';
 END IF;
 RETURN QUERY SELECT m.id,a.canonical_email,a.display_name,m.status,t.requests,t.prompt_tokens,t.completion_tokens,
   t.estimated_requests,t.error_requests,t.cost_micros,t.unpriced_requests
  FROM (SELECT d.membership_id AS member,sum(d.requests)::bigint AS requests,sum(d.prompt_tokens)::bigint AS prompt_tokens,
    sum(d.completion_tokens)::bigint AS completion_tokens,sum(d.estimated_requests)::bigint AS estimated_requests,
    sum(d.error_requests)::bigint AS error_requests,sum(d.cost_micros)::bigint AS cost_micros,
    sum(d.unpriced_requests)::bigint AS unpriced_requests
   FROM forge.usage_daily d WHERE d.organization_id=org AND d.day BETWEEN first_day AND last_day GROUP BY d.membership_id) t
  JOIN forge.memberships m ON m.organization_id=org AND m.id=t.member
  JOIN forge.owned_accounts a ON a.id=m.identity_id
  WHERE after_member IS NULL OR m.id>after_member ORDER BY m.id LIMIT page;
END $$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_directory_authority;
REVOKE ALL ON FUNCTION forge.usage_company_members(text,uuid,date,date,uuid,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.usage_company_members(text,uuid,date,date,uuid,integer) TO forge_gateway_service;
COMMIT;

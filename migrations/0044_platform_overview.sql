-- Platform overview and per-day usage series. Additive and forward-only.
-- * ``platform_overview`` is one read for the console's first page: how many companies are active and suspended, how many different
--   people used Forge in the range, the same seven counters the platform totals report, and the five figures of the previous period
--   (the same number of days immediately before the range) that the page needs for "change against the previous period".
-- * ``platform_usage_days`` is the daily series of the rollup over the range, one row per UTC day IN ORDER (days without usage are
--   zeros, so a chart needs no gap filling) with the number of different people active that day.
-- Both re-validate a fresh verified platform owner on every call and use the existing bounded range check (at most 366 days). They
-- read only the daily rollup and the company list through the policies the platform authority already holds, so they carry counters
-- and integers in micro-USD, never content. No login role gains a table privilege.
BEGIN;
SET LOCAL lock_timeout='2s';
SET LOCAL statement_timeout='10s';
GRANT CREATE ON SCHEMA forge TO forge_platform_authority;
SET LOCAL ROLE forge_platform_authority;
CREATE FUNCTION forge.platform_overview(digest text,first_day date,last_day date)
RETURNS TABLE(companies_active bigint,companies_suspended bigint,active_users bigint,requests bigint,prompt_tokens bigint,
 completion_tokens bigint,estimated_requests bigint,error_requests bigint,cost_micros bigint,unpriced_requests bigint,
 previous_active_users bigint,previous_requests bigint,previous_prompt_tokens bigint,previous_completion_tokens bigint,
 previous_cost_micros bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE span integer; before_first date; before_last date; live bigint; paused bigint;
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 PERFORM forge.platform_usage_range(first_day,last_day,1);
 span:=last_day-first_day+1; before_last:=first_day-1; before_first:=first_day-span;
 PERFORM set_config('forge.platform_list','1',true);
 SELECT count(*) FILTER (WHERE o.active),count(*) FILTER (WHERE NOT o.active) INTO live,paused FROM forge.organizations o;
 PERFORM set_config('forge.platform_list','',true);
 RETURN QUERY SELECT live,paused,cur.people,cur.hits,cur.prompt,cur.completion,cur.estimated,cur.failed,cur.cost,cur.unpriced,
   old.people,old.hits,old.prompt,old.completion,old.cost
  FROM (SELECT count(DISTINCT d.membership_id)::bigint AS people,coalesce(sum(d.requests),0)::bigint AS hits,
    coalesce(sum(d.prompt_tokens),0)::bigint AS prompt,coalesce(sum(d.completion_tokens),0)::bigint AS completion,
    coalesce(sum(d.estimated_requests),0)::bigint AS estimated,coalesce(sum(d.error_requests),0)::bigint AS failed,
    coalesce(sum(d.cost_micros),0)::bigint AS cost,coalesce(sum(d.unpriced_requests),0)::bigint AS unpriced
   FROM forge.usage_daily d WHERE d.day BETWEEN first_day AND last_day) cur,
  (SELECT count(DISTINCT d.membership_id)::bigint AS people,coalesce(sum(d.requests),0)::bigint AS hits,
    coalesce(sum(d.prompt_tokens),0)::bigint AS prompt,coalesce(sum(d.completion_tokens),0)::bigint AS completion,
    coalesce(sum(d.cost_micros),0)::bigint AS cost
   FROM forge.usage_daily d WHERE d.day BETWEEN before_first AND before_last) old;
END $$;

CREATE FUNCTION forge.platform_usage_days(digest text,first_day date,last_day date)
RETURNS TABLE(day date,requests bigint,prompt_tokens bigint,completion_tokens bigint,estimated_requests bigint,
 error_requests bigint,cost_micros bigint,unpriced_requests bigint,active_users bigint)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
 PERFORM forge.platform_lock_owner(digest,false);
 PERFORM forge.platform_usage_range(first_day,last_day,1);
 RETURN QUERY SELECT first_day+g.step,coalesce(t.hits,0)::bigint,coalesce(t.prompt,0)::bigint,coalesce(t.completion,0)::bigint,
   coalesce(t.estimated,0)::bigint,coalesce(t.failed,0)::bigint,coalesce(t.cost,0)::bigint,coalesce(t.unpriced,0)::bigint,
   coalesce(t.people,0)::bigint
  FROM generate_series(0,last_day-first_day) AS g(step)
  LEFT JOIN (SELECT u.day AS usage_day,sum(u.requests) AS hits,sum(u.prompt_tokens) AS prompt,sum(u.completion_tokens) AS completion,
    sum(u.estimated_requests) AS estimated,sum(u.error_requests) AS failed,sum(u.cost_micros) AS cost,
    sum(u.unpriced_requests) AS unpriced,count(DISTINCT u.membership_id) AS people
   FROM forge.usage_daily u WHERE u.day BETWEEN first_day AND last_day GROUP BY u.day) t ON t.usage_day=first_day+g.step
  ORDER BY g.step;
END $$;
RESET ROLE;
REVOKE CREATE ON SCHEMA forge FROM forge_platform_authority;
REVOKE ALL ON FUNCTION forge.platform_overview(text,date,date),forge.platform_usage_days(text,date,date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION forge.platform_overview(text,date,date),forge.platform_usage_days(text,date,date) TO forge_platform_service;
COMMIT;

import { Activity, Info } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { BarChart } from "../../charts/BarChart";
import { RangePicker } from "../../components/usage/RangePicker";
import { useDays } from "../../components/usage/useDays";
import { formatCostMicros, formatTokens } from "../../lib/format";
import { windowFor } from "../../platform/range";
import { tokensOf } from "../../platform/usage";
import { errorMessage } from "../../shell/errors";
import { Alert } from "../../ui/Alert";
import { Button, buttonVariants } from "../../ui/Button";
import { EmptyState } from "../../ui/EmptyState";
import { PageHeader } from "../../ui/PageHeader";
import { Skeleton } from "../../ui/Skeleton";
import { Stat } from "../../ui/Stat";
import { usePortal } from "./PortalLayout";

export function Usage() {
  const { services, organization } = usePortal();
  const [days, setDays] = useDays();
  const window = windowFor(days);
  const usage = useQuery({ queryKey: ["portal", "usage", organization.id, window], queryFn: () => services.usage.mine(organization.id, window), retry: false });

  return (
    <section className="flex flex-col gap-6">
      <PageHeader title="My usage" description="What you have used through Forge. Only you can see this." actions={<RangePicker days={days} onChange={setDays} />} />
      {usage.isPending && <Skeleton className="h-40 w-full" />}
      {usage.isError && <Alert tone="destructive" action={<Button size="sm" variant="outline" onClick={() => void usage.refetch()}>Try again</Button>}>{errorMessage(usage.error)}</Alert>}
      {usage.isSuccess && usage.data === null && (
        <EmptyState icon={Info} title="Usage reporting is not available yet" hint="This Forge server cannot show your personal usage yet. Nothing is wrong with your account." />
      )}
      {usage.data && usage.data.requests === 0 && (
        <EmptyState icon={Activity} title="No usage yet" hint="Usage appears here after your first conversation in the Forge app." action={<Link to="/portal/download" className={buttonVariants({})}>Download Prometheon Forge</Link>} />
      )}
      {usage.data && usage.data.requests > 0 && (
        <>
          <section aria-label="My usage">
            <dl className="grid gap-4 sm:grid-cols-3">
              <Stat label="Tokens">{formatTokens(tokensOf(usage.data))}</Stat>
              <Stat label="Requests">{usage.data.requests.toLocaleString("en-US")}</Stat>
              <Stat label="Cost">{formatCostMicros(usage.data.cost_micros)}</Stat>
            </dl>
          </section>
          <BarChart id="my-token-split" title="Prompt and completion tokens" items={[{ label: "Prompt", value: usage.data.prompt_tokens }, { label: "Completion", value: usage.data.completion_tokens }]} />
        </>
      )}
    </section>
  );
}
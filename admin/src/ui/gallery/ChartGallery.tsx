import { Donut } from "../../charts/Donut";
import { BarChart } from "../../charts/BarChart";
import { Sparkline } from "../../charts/Sparkline";
import { StackedBars } from "../../charts/StackedBars";
import { AreaChart, type TimeSeries } from "../../charts/TimeSeriesChart";
import { Card, CardContent } from "../Card";

const DAILY: TimeSeries = {
  id: "tokens",
  label: "Tokens",
  points: Array.from({ length: 30 }, (_, index) => ({ t: Date.UTC(2026, 9, 1 + index), v: 30_000 + ((index * 7919) % 20_000) })),
};
const MODELS = [
  { label: "gpt-4o-mini", value: 90_000 },
  { label: "gpt-4o", value: 1_200_000 },
  { label: "claude-3-5-sonnet", value: 800_000 },
];
const MANY = ["a", "b", "c", "d", "e", "f", "g", "h", "i"].map((name, index) => ({ label: `model-${name}`, value: 900 - index * 80 }));

/** Test-build gallery of the chart kit: the data variants and the loading, empty and error states. */
export function ChartGallery() {
  return (
    <main className="mx-auto flex max-w-4xl flex-col gap-8 bg-app p-6 font-body text-body text-fg">
      <h1 className="font-title text-page font-bold">Chart kit</h1>
      <p className="flex items-center gap-3">
        Tokens <Sparkline label="Tokens" values={[12_000, 30_000, 25_000, 60_000, 98_000]} />
      </p>
      <Card>
        <CardContent className="pt-5">
          <AreaChart id="daily" title="Daily tokens" series={[DAILY]} />
        </CardContent>
      </Card>
      <div className="grid gap-6 md:grid-cols-2">
        <Card><CardContent className="pt-5"><BarChart id="ranked" title="Tokens by model" items={MODELS} /></CardContent></Card>
        <Card><CardContent className="pt-5"><StackedBars id="share" title="Share by model" items={MODELS} /></CardContent></Card>
      </div>
      <Card><CardContent className="pt-5"><Donut id="donut" title="Requests by model" items={MANY} format={(value) => String(value)} /></CardContent></Card>
      <div className="grid gap-6 md:grid-cols-3">
        <AreaChart id="loading" title="Daily cost" series={[]} loading />
        <AreaChart id="empty" title="Cost by day" series={[]} emptyMessage="No usage in this period" />
        <AreaChart id="error" title="Cost" series={[]} error="Could not load cost" onRetry={() => undefined} />
      </div>
    </main>
  );
}
import { useTranslation } from "react-i18next";
import { RANGES, type Days } from "../../platform/range";
import { Button } from "../../ui/Button";

/** 7 / 30 / 90 days as a toggle group. */
export function RangePicker({ days, onChange }: { days: Days; onChange: (days: Days) => void }) {
  const { t } = useTranslation();
  return (
    <div role="group" aria-label={t("usage.rangeLabel")} className="inline-flex gap-1 rounded-control border border-line bg-surface p-1">
      {RANGES.map((value) => (
        <Button key={value} size="sm" variant={value === days ? "default" : "ghost"} aria-pressed={value === days} onClick={() => onChange(value)}>
          {t("usage.days", { days: value })}
        </Button>
      ))}
    </div>
  );
}

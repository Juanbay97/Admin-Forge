import { Building2, Gauge, Layers, Palette, PlugZap, ShieldCheck, Users, type LucideIcon } from "lucide-react";
import type { IconName } from "./areas";

const ICONS: Record<IconName, LucideIcon> = {
  gauge: Gauge,
  users: Users,
  plug: PlugZap,
  layers: Layers,
  palette: Palette,
  shield: ShieldCheck,
  building: Building2,
};

export function NavIcon({ name, className }: { name: IconName; className?: string }) {
  const Icon = ICONS[name];
  return <Icon aria-hidden="true" className={className} />;
}
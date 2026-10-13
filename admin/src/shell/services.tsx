import { createContext, useContext, type ReactNode } from "react";
import type { Services } from "../api/services";

const ServicesContext = createContext<Services | null>(null);

/** Services stay injectable so UI tests and area changes can supply their own ports. */
export function ServicesProvider({ services, children }: { services: Services; children: ReactNode }) {
  return <ServicesContext.Provider value={services}>{children}</ServicesContext.Provider>;
}

export function useServices(): Services {
  const services = useContext(ServicesContext);
  if (!services) throw new Error("useServices needs a ServicesProvider");
  return services;
}
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { services as runtimeServices } from "../api/runtime";
import type { Services } from "../api/services";
import { ApiError } from "../api/client";
import { session } from "../auth/session";
import { ToastProvider } from "../ui/toast/Toast";
import { ServicesProvider } from "./services";

const isClientError = (error: unknown) => error instanceof ApiError && error.status >= 400 && error.status < 500;

/** staleTime 30s, no retry on 4xx; a 401 from any query or mutation drops the session (the shell then shows sign-in). */
export function createQueryClient(onUnauthorized: () => void = () => session.clear()): QueryClient {
  const handle = (error: unknown) => {
    if (error instanceof ApiError && error.status === 401) onUnauthorized();
  };
  return new QueryClient({
    queryCache: new QueryCache({ onError: handle }),
    mutationCache: new MutationCache({ onError: handle }),
    defaultOptions: {
      queries: { staleTime: 30_000, retry: (count, error) => !isClientError(error) && count < 1, refetchOnWindowFocus: false },
    },
  });
}

export function Providers({ children, services = runtimeServices }: { children: ReactNode; services?: Services }) {
  const [client] = useState(() => createQueryClient());
  // Signing out or expiring leaves nothing of the previous account in the cache.
  useEffect(() => session.subscribe(() => { if (!session.token()) client.clear(); }), [client]);
  return (
    <QueryClientProvider client={client}>
      <ServicesProvider services={services}>
        <ToastProvider>{children}</ToastProvider>
      </ServicesProvider>
    </QueryClientProvider>
  );
}
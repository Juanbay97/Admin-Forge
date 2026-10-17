import { AlertTriangle, CheckCircle2, Info, X, XCircle, type LucideIcon } from "lucide-react";
import { createContext, useContext, useState, useSyncExternalStore, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { cn } from "../../lib/cn";
import { createToastStore, type ToastInput, type ToastStore, type ToastTone } from "./store";

const ToastContext = createContext<ToastStore | null>(null);

export function ToastProvider({ children, store: provided }: { children: ReactNode; store?: ToastStore }) {
  const [store] = useState(() => provided ?? createToastStore());
  return (
    <ToastContext.Provider value={store}>
      {children}
      <ToastRegion store={store} />
    </ToastContext.Provider>
  );
}

export function useToast(): { push: (input: ToastInput) => string; dismiss: (id: string) => void } {
  const store = useContext(ToastContext);
  if (!store) throw new Error("useToast needs a ToastProvider");
  return { push: store.push, dismiss: store.dismiss };
}

const ICONS: Record<ToastTone, LucideIcon> = { info: Info, success: CheckCircle2, warning: AlertTriangle, destructive: XCircle };
const TONES: Record<ToastTone, string> = {
  info: "text-on-action-soft",
  success: "text-on-ok-soft",
  warning: "text-on-warn-soft",
  destructive: "text-on-danger-soft",
};

/** The live region is always mounted, so a toast added later is announced politely. */
function ToastRegion({ store }: { store: ToastStore }) {
  const { t } = useTranslation();
  const toasts = useSyncExternalStore(store.subscribe, store.list, store.list);
  return (
    <div
      role="region"
      aria-label={t("ui.toast.notifications")}
      aria-live="polite"
      className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col items-end gap-2 sm:left-auto sm:w-96"
    >
      {toasts.map((toast) => {
        const Icon = ICONS[toast.tone];
        return (
          <div
            key={toast.id}
            className="pointer-events-auto flex w-full items-start gap-3 rounded-card border border-line bg-raised p-4 text-body text-fg shadow-overlay"
          >
            <Icon aria-hidden="true" className={cn("mt-0.5 size-5 shrink-0", TONES[toast.tone])} />
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <p className="font-semibold">{toast.title}</p>
              {toast.message && <p className="text-muted">{toast.message}</p>}
            </div>
            <button
              type="button"
              aria-label={t("ui.toast.dismiss", { title: toast.title })}
              onClick={() => store.dismiss(toast.id)}
              className="-m-2 flex size-10 shrink-0 items-center justify-center rounded-control text-muted outline-focus hover:bg-subtle focus-visible:outline-2"
            >
              <X aria-hidden="true" className="size-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import { useI18n } from "@/i18n";

type Tone = "success" | "error";
interface Toast {
  id: number;
  message: string;
  tone: Tone;
}

interface ToastApi {
  toast: (message: string, tone?: Tone) => void;
}

const ToastContext = createContext<ToastApi>({ toast: () => undefined });

/** Brief confirmations that do not steal focus. Announced politely to screen readers. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback((message: string, tone: Tone = "success") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), 4000);
  }, []);

  // Raised by the query client when a request never reached the server.
  const { t } = useI18n();
  useEffect(() => {
    const onOffline = () => toast(t("toast.offline"), "error");
    window.addEventListener("shabetz:offline", onOffline);
    return () => window.removeEventListener("shabetz:offline", onOffline);
  }, [toast, t]);

  const value = useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed bottom-4 end-4 z-[60] flex max-w-sm flex-col gap-2 print:hidden"
      >
        {toasts.map(({ id, message, tone }) => (
          <div
            key={id}
            className="pointer-events-auto flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm shadow-lg dark:border-slate-700 dark:bg-slate-900"
          >
            {tone === "success" ? (
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
            ) : (
              <XCircle className="h-4 w-4 shrink-0 text-red-600" aria-hidden />
            )}
            {message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

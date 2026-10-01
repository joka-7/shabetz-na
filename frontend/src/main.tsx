import React from "react";
import ReactDOM from "react-dom/client";
import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { ToastProvider } from "@/components/Toasts";
import { App } from "./App";
import { SessionProvider } from "@/hooks/useSession";
import { I18nProvider } from "@/i18n";
import "./index.css";

const queryClient = new QueryClient({
  // A request that never reached the server has no message of its own, so no
  // screen explains it. Failures the server answered are shown where they happen.
  mutationCache: new MutationCache({
    onError: (error) => {
      if (!(error instanceof ApiError)) window.dispatchEvent(new Event("shabetz:offline"));
    },
  }),
  defaultOptions: {
    queries: {
      // Configuration is edited by people, not streamed, so refetching on every
      // window focus is noise rather than freshness.
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30_000,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <I18nProvider>
      <ToastProvider>
        <ErrorBoundary>
          <QueryClientProvider client={queryClient}>
            <SessionProvider>
              <App />
            </SessionProvider>
          </QueryClientProvider>
        </ErrorBoundary>
      </ToastProvider>
    </I18nProvider>
  </React.StrictMode>,
);

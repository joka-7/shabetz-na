import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";
import { SessionProvider } from "@/hooks/useSession";
import { I18nProvider } from "@/i18n";
import "./index.css";

const queryClient = new QueryClient({
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
      <QueryClientProvider client={queryClient}>
        <SessionProvider>
          <App />
        </SessionProvider>
      </QueryClientProvider>
    </I18nProvider>
  </React.StrictMode>,
);

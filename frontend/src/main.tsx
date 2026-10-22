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
// Bundled rather than fetched from Google: works offline in the desktop app,
// and visitors' addresses are not handed to a third party on every page view.
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/heebo/400.css";
import "@fontsource/heebo/500.css";
import "@fontsource/heebo/600.css";
import "@fontsource/heebo/700.css";

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

// Mobile browsers skip :active/tap-highlight rendering on pages with no
// touch listeners (treated as passively scrollable) -- this one-time no-op
// listener makes tap feedback on the footer icon links actually render.
document.addEventListener("touchstart", () => {}, { passive: true });

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

// The installed app's offline shell; only in a built app, where the files it
// caches exist.
if (import.meta.env.PROD && "serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Optional: without it the app simply needs the network, as before.
    });
  });
}

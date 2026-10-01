import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { useI18n } from "@/i18n";

function Fallback({ onReload }: { onReload: () => void }) {
  const { t } = useI18n();
  return (
    <div role="alert" className="mx-auto mt-24 max-w-md space-y-3 p-6 text-center">
      <h1 className="text-lg font-semibold">{t("boundary.title")}</h1>
      <p className="text-sm text-slate-500">{t("boundary.hint")}</p>
      <button className="btn-primary" onClick={onReload}>
        {t("boundary.reload")}
      </button>
    </div>
  );
}

/**
 * A crash in one screen should not leave a blank page. Whatever was on screen
 * is unsaved only if it was never sent, so reloading is always safe.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled interface error", error, info.componentStack);
  }

  render() {
    return this.state.failed ? (
      <Fallback onReload={() => window.location.reload()} />
    ) : (
      this.props.children
    );
  }
}

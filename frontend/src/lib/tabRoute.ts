/**
 * The open tab, kept in the address bar.
 *
 * Without it the phone's back gesture left the app instead of going back a
 * tab, a refresh always landed on the schedule, and no tab could be linked to.
 */

import { useCallback, useEffect, useState } from "react";

export type Tab = "dashboard" | "config" | "timeoff" | "swaps";

const PATHS: Record<Tab, string> = {
  dashboard: "/",
  timeoff: "/time-off",
  swaps: "/swaps",
  config: "/configuration",
};

/** The tab a path names; anything unknown opens the schedule. */
export function tabFromPath(path: string): Tab {
  const clean = path.replace(/\/+$/, "") || "/";
  const found = (Object.keys(PATHS) as Tab[]).find((tab) => PATHS[tab] === clean);
  return found ?? "dashboard";
}

export function pathForTab(tab: Tab): string {
  return PATHS[tab];
}

export function useTabRoute(): [Tab, (tab: Tab) => void] {
  const [tab, setTabState] = useState<Tab>(() => tabFromPath(window.location.pathname));

  useEffect(() => {
    const onPop = () => setTabState(tabFromPath(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const setTab = useCallback((next: Tab) => {
    setTabState(next);
    const path = pathForTab(next);
    if (window.location.pathname !== path) window.history.pushState(null, "", path);
  }, []);

  return [tab, setTab];
}

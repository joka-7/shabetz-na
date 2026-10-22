import { useInfiniteQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { EmptyState, Spinner } from "@/components/ui";
import { useI18n } from "@/i18n";

interface ActivityEntry {
  id: number;
  at: string;
  user_name: string | null;
  entity_type: string;
  entity_id: string | null;
  action: string;
}

const PAGE = 50;

/** Who changed what in the project, newest first: the audit log the server already keeps. */
export function ActivityLog() {
  const { t } = useI18n();
  const log = useInfiniteQuery({
    queryKey: ["activity"],
    initialPageParam: null as number | null,
    queryFn: ({ pageParam }) =>
      api.get<ActivityEntry[]>(
        `/api/project/activity?limit=${PAGE}${pageParam ? `&before=${pageParam}` : ""}`,
      ),
    getNextPageParam: (last) => (last.length === PAGE ? last[last.length - 1]!.id : null),
  });
  const entries = log.data?.pages.flat() ?? [];
  const when = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold">{t("activity.title")}</h2>
        <p className="text-sm text-slate-500">{t("activity.intro")}</p>
      </div>
      {log.isLoading ? (
        <Spinner />
      ) : !entries.length ? (
        <EmptyState title={t("activity.empty")} hint="" />
      ) : (
        <ul className="divide-y divide-slate-200 text-sm dark:divide-slate-700">
          {entries.map((entry) => (
            <li key={entry.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-2">
              <time className="w-40 shrink-0 text-xs text-slate-500" dateTime={entry.at}>
                {when.format(new Date(entry.at))}
              </time>
              <span className="font-medium">{entry.user_name ?? t("activity.someone")}</span>
              <span>
                {entry.action} · {entry.entity_type.replace(/_/g, " ")}
                {entry.entity_id ? ` #${entry.entity_id.slice(0, 10)}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
      {log.hasNextPage && (
        <button className="btn-ghost text-sm" onClick={() => void log.fetchNextPage()} disabled={log.isFetchingNextPage}>
          {t("activity.more")}
        </button>
      )}
    </div>
  );
}

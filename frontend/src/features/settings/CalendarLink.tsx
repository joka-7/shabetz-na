import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, Copy } from "lucide-react";
import { api } from "@/api/client";
import { MutationError } from "@/features/setup/steps/parts";
import { useI18n } from "@/i18n";

interface CalendarLinkState {
  enabled: boolean;
  path: string | null;
}

const KEY = ["calendar-link"] as const;

/**
 * A personal calendar address for the published shifts.
 *
 * The server keeps only a hash of it, so the full address can be shown just
 * once, right after it is made; making another one retires the old one.
 */
export function CalendarLink() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const status = useQuery({
    queryKey: KEY,
    queryFn: () => api.get<CalendarLinkState>("/api/me/calendar"),
  });
  const [url, setUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const create = useMutation({
    mutationFn: () => api.post<CalendarLinkState>("/api/me/calendar"),
    onSuccess: (made) => {
      setUrl(made.path ? `${window.location.origin}${made.path}` : null);
      setCopied(false);
      queryClient.setQueryData(KEY, { enabled: true, path: null });
    },
  });
  const remove = useMutation({
    mutationFn: () => api.del("/api/me/calendar"),
    onSuccess: () => {
      setUrl(null);
      queryClient.setQueryData(KEY, { enabled: false, path: null });
    },
  });

  const enabled = status.data?.enabled ?? false;

  return (
    <div className="space-y-2">
      <h3 className="text-xs font-semibold text-slate-500">{t("calendar.heading")}</h3>
      <p className="text-xs text-slate-500">{t("calendar.intro")}</p>

      {url && (
        <div className="space-y-2">
          <input className="input text-xs" readOnly value={url} aria-label={t("calendar.heading")} onFocus={(e) => e.target.select()} />
          <div className="flex flex-wrap gap-2">
            <button
              className="btn-ghost text-sm"
              onClick={() => {
                void navigator.clipboard?.writeText(url).then(() => setCopied(true));
              }}
            >
              <Copy className="h-4 w-4" aria-hidden />
              {copied ? t("calendar.copied") : t("calendar.copy")}
            </button>
            {/* Apple Calendar and Outlook subscribe from a webcal: link directly. */}
            <a className="btn-ghost text-sm" href={url.replace(/^https?:/, "webcal:")}>
              <CalendarPlus className="h-4 w-4" aria-hidden />
              {t("calendar.open")}
            </a>
          </div>
          <p className="text-xs text-amber-700 dark:text-amber-400">{t("calendar.private")}</p>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <button className="btn-primary text-sm" onClick={() => create.mutate()} disabled={create.isPending}>
          {enabled ? t("calendar.replace") : t("calendar.create")}
        </button>
        {enabled && (
          <button className="btn-ghost text-sm" onClick={() => remove.mutate()} disabled={remove.isPending}>
            {t("calendar.remove")}
          </button>
        )}
      </div>
      <MutationError error={create.error ?? remove.error} />
    </div>
  );
}

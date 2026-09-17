import { Download } from "lucide-react";
import { downloadExport } from "@/api/client";
import { useSession } from "@/hooks/useSession";

const LABELS: Record<string, string> = { csv: "CSV", html: "HTML", pdf: "PDF" };

/**
 * Only the formats the deployment can actually produce are offered.
 *
 * PDF rendering needs system libraries that are often missing, so the server
 * reports what it supports and a format it cannot produce is left out rather
 * than presented as a button that fails.
 */
export function ExportBar({ scheduleId }: { scheduleId: string }) {
  const { capabilities } = useSession();
  const formats = capabilities?.export_formats ?? [];

  if (formats.length === 0) return null;

  return (
    <div className="flex items-center gap-2">
      <span className="label mb-0">Download</span>
      {formats.map((format) => (
        <button
          key={format}
          className="btn-ghost text-sm"
          onClick={() => downloadExport(scheduleId, format)}
        >
          <Download className="h-4 w-4" aria-hidden />
          {LABELS[format] ?? format.toUpperCase()}
        </button>
      ))}
    </div>
  );
}

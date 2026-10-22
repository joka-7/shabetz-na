import { useState } from "react";
import { Check, Copy, MessageCircle } from "lucide-react";
import { useI18n } from "@/i18n";
import { whatsappLink } from "@/lib/share";

/**
 * A message ready to send: shown as it will read, with one button to copy it
 * and one to open WhatsApp with it already typed.
 */
export function ShareBox({ text, label }: { text: string; label: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);
  const link = whatsappLink(text);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Clipboard access can be refused; selecting the text is the fallback.
      const area = document.getElementById("share-text") as HTMLTextAreaElement | null;
      area?.select();
      return;
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-2">
      <label className="label" htmlFor="share-text">{label}</label>
      <textarea
        id="share-text"
        className="input min-h-48 font-mono text-xs"
        readOnly
        value={text}
        onFocus={(event) => event.currentTarget.select()}
      />
      <div className="flex flex-wrap items-center gap-2">
        <button className="btn-primary" onClick={() => void copy()}>
          {copied ? <Check className="h-4 w-4" aria-hidden /> : <Copy className="h-4 w-4" aria-hidden />}
          {copied ? t("share.copied") : t("share.copy")}
        </button>
        {link ? (
          <a className="btn-ghost" href={link} target="_blank" rel="noreferrer">
            <MessageCircle className="h-4 w-4" aria-hidden />
            {t("share.whatsapp")}
          </a>
        ) : (
          <span className="text-xs text-slate-500">{t("share.tooLong")}</span>
        )}
      </div>
      <p className="text-xs text-slate-500">{t("share.hint")}</p>
    </div>
  );
}

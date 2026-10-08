import { useEffect, useState } from "react";
import { Download, Smartphone } from "lucide-react";
import { useI18n } from "@/i18n";

const REPO = "joka-7/shabetz-na";
const RELEASES = `https://github.com/${REPO}/releases/latest`;

interface ReleaseAsset {
  name: string;
  browser_download_url: string;
}

/** The browser's "install this site as an app" prompt, where it offers one. */
interface InstallPrompt extends Event {
  prompt: () => Promise<void>;
}

/**
 * Where to get the app: the Windows installer, an Android file if one has been
 * attached to the release, and the website itself installed on a phone.
 *
 * The files are looked up on the latest release rather than hard-coded, since
 * their names carry the version; the Android file is shown only if it exists,
 * so publishing one later needs no change here.
 */
export function GetTheApp() {
  const { t } = useI18n();
  const [assets, setAssets] = useState<ReleaseAsset[]>([]);
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`https://api.github.com/repos/${REPO}/releases/latest`, { signal: controller.signal })
      .then((response) => (response.ok ? response.json() : null))
      .then((release: { assets?: ReleaseAsset[] } | null) => setAssets(release?.assets ?? []))
      .catch(() => undefined); // offline or rate-limited: the plain releases link still works
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const onPrompt = (event: Event) => {
      event.preventDefault();
      setPrompt(event as InstallPrompt);
    };
    window.addEventListener("beforeinstallprompt", onPrompt);
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);

  const windows = assets.find((a) => /^Shabetz-Setup-.*\.exe$/.test(a.name));
  const android = assets.find((a) => a.name.toLowerCase().endsWith(".apk"));
  const iPhone = /iphone|ipad|ipod/i.test(navigator.userAgent);

  return (
    <div className="space-y-2">
      <a className="btn-ghost w-full justify-start" href={windows?.browser_download_url ?? RELEASES} target="_blank" rel="noreferrer">
        <Download className="h-4 w-4" aria-hidden />
        {t("getapp.windows")}
      </a>
      {android && (
        <a className="btn-ghost w-full justify-start" href={android.browser_download_url} rel="noreferrer">
          <Smartphone className="h-4 w-4" aria-hidden />
          {t("getapp.android")}
        </a>
      )}
      {prompt && (
        <button className="btn-ghost w-full justify-start" onClick={() => void prompt.prompt()}>
          <Smartphone className="h-4 w-4" aria-hidden />
          {t("getapp.install")}
        </button>
      )}
      <p className="text-xs text-slate-500">{iPhone ? t("getapp.hintIphone") : t("getapp.hintPhone")}</p>
    </div>
  );
}

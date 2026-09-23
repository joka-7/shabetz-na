/**
 * Interface language.
 *
 * Two dictionaries with identical keys: `he` is typed against `en`, so a
 * string added in one place and forgotten in the other fails the type check
 * rather than showing up as a raw key on screen.
 *
 * Only the interface is translated. Names the administrator types — divisions,
 * skills, jobs, people — are shown exactly as entered.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { en } from "./en";
import { he } from "./he";

export type Lang = "en" | "he";
export type MessageKey = keyof typeof en;
export type Params = Record<string, string | number>;

/** Keys that exist in both a `_one` and an `_other` form. */
export type PluralKey = {
  [K in MessageKey]: K extends `${infer Base}_one`
    ? `${Base}_other` extends MessageKey
      ? Base
      : never
    : never;
}[MessageKey];

const DICTIONARIES: Record<Lang, Record<MessageKey, string>> = { en, he };
const STORAGE_KEY = "shabetz.lang";

export function translate(lang: Lang, key: MessageKey, params?: Params): string {
  const template = DICTIONARIES[lang][key] ?? en[key];
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in params ? String(params[name]) : match,
  );
}

export function translatePlural(
  lang: Lang,
  base: PluralKey,
  count: number,
  params?: Params,
): string {
  const key = `${base}_${count === 1 ? "one" : "other"}` as MessageKey;
  return translate(lang, key, { count, ...params });
}

function initialLang(): Lang {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "he") return stored;
  } catch {
    // Storage can be unavailable (private windows, blocked site data); the
    // browser's own language is a reasonable answer then.
  }
  return navigator.language?.toLowerCase().startsWith("he") ? "he" : "en";
}

interface I18n {
  lang: Lang;
  dir: "ltr" | "rtl";
  setLang: (lang: Lang) => void;
  t: (key: MessageKey, params?: Params) => string;
  tn: (base: PluralKey, count: number, params?: Params) => string;
  /** A calendar date (YYYY-MM-DD) in the interface language. */
  formatDate: (isoDate: string, options?: Intl.DateTimeFormatOptions) => string;
  weekdayShort: (weekday: number) => string;
  /** Weekdays in the order this language's calendars show them. */
  weekdayOrder: readonly number[];
}

const I18nContext = createContext<I18n | null>(null);

/** Python's weekday numbering, which the server uses: Monday is 0. */
const REFERENCE_MONDAY = Date.UTC(2024, 0, 1);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const dir = lang === "he" ? "rtl" : "ltr";

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = dir;
  }, [lang, dir]);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Remembering the choice is a convenience; the switch itself still works.
    }
  }, []);

  const value = useMemo<I18n>(() => {
    const locale = lang === "he" ? "he-IL" : "en-GB";
    const weekdayFormat = new Intl.DateTimeFormat(locale, { weekday: "short", timeZone: "UTC" });
    return {
      lang,
      dir,
      setLang,
      t: (key, params) => translate(lang, key, params),
      tn: (base, count, params) => translatePlural(lang, base, count, params),
      formatDate: (isoDate, options = { day: "numeric", month: "short", year: "numeric" }) => {
        const [y, m, d] = isoDate.split("-").map(Number);
        if (!y || !m || !d) return isoDate;
        return new Intl.DateTimeFormat(locale, { ...options, timeZone: "UTC" }).format(
          new Date(Date.UTC(y, m - 1, d)),
        );
      },
      weekdayShort: (weekday) =>
        weekdayFormat.format(new Date(REFERENCE_MONDAY + weekday * 86_400_000)),
      // An Israeli week starts on Sunday.
      weekdayOrder: lang === "he" ? [6, 0, 1, 2, 3, 4, 5] : [0, 1, 2, 3, 4, 5, 6],
    };
  }, [lang, dir, setLang]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside I18nProvider");
  return value;
}

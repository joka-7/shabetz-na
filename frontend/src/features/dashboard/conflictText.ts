import type { MessageKey, Params } from "@/i18n";

type Translate = (key: MessageKey, params?: Params) => string;

const CONFLICT_KEYS: Record<string, MessageKey> = {
  UNAVAILABLE: "conflict.UNAVAILABLE",
  DOUBLE_BOOKED: "conflict.DOUBLE_BOOKED",
  REST_VIOLATION: "conflict.REST_VIOLATION",
  MISSING_SKILL: "conflict.MISSING_SKILL",
};

/** Kinds that record a rule broken by a hand edit, as opposed to a coverage gap. */
export const isConflictKind = (kind: string): boolean => kind in CONFLICT_KEYS;

/**
 * A rule broken by a hand edit, in the interface language. `fallback` is the
 * server's English, used only for a kind this build does not know.
 */
export function conflictText(
  t: Translate,
  kind: string,
  params: { person: string; job: string; window: string; date: string },
  fallback: string,
): string {
  const key = CONFLICT_KEYS[kind];
  return key ? t(key, params) : fallback;
}

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { Sodium } from "@/lib/memberKeys";
import { useSession } from "@/hooks/useSession";

/**
 * The unlocked secret key, held in memory for this tab only.
 *
 * It is never written to storage: a reload or sign-out forgets it, and the
 * member unlocks again with their passphrase. The key is stored together with
 * the account it was unlocked for and only handed out while that account is
 * signed in, so after switching accounts — even mid-unlock — no screen can
 * see the previous account's key.
 */
interface MemberKeyState {
  secretKey: Uint8Array | null;
  remember: (secretKey: Uint8Array) => void;
  forget: () => void;
}

const MemberKeyContext = createContext<MemberKeyState | null>(null);

export function MemberKeyProvider({ children }: { children: ReactNode }) {
  const { user } = useSession();
  const userId = user?.id ?? null;
  const [held, setHeld] = useState<{ userId: number; key: Uint8Array } | null>(null);

  const remember = useCallback(
    (key: Uint8Array) => setHeld(userId === null ? null : { userId, key }),
    [userId],
  );
  const forget = useCallback(() => setHeld(null), []);
  const secretKey = held !== null && held.userId === userId ? held.key : null;
  const value = useMemo(() => ({ secretKey, remember, forget }), [secretKey, remember, forget]);

  return <MemberKeyContext.Provider value={value}>{children}</MemberKeyContext.Provider>;
}

export function useMemberKey(): MemberKeyState {
  const context = useContext(MemberKeyContext);
  if (!context) throw new Error("useMemberKey must be used inside MemberKeyProvider");
  return context;
}

let sodiumLoad: Promise<Sodium> | null = null;

/**
 * libsodium, loaded on first use: about half a megabyte of WebAssembly that
 * only the encryption screens need, so it stays out of the main bundle. A
 * failed load is forgotten, so the next attempt tries again.
 */
export function loadSodium(): Promise<Sodium> {
  sodiumLoad ??= import("libsodium-wrappers-sumo")
    .then(async (module) => {
      const sodium = module.default;
      await sodium.ready;
      return sodium;
    })
    .catch((error: unknown) => {
      sodiumLoad = null;
      throw error;
    });
  return sodiumLoad;
}

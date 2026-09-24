/**
 * Google sign-in through Firebase Authentication.
 *
 * The browser only uses Firebase to get a Google-signed ID token; the server
 * checks that token and opens its own session, so nothing else here talks to
 * Firebase. The SDK is loaded on first use, which keeps it out of the desktop
 * app, where sign-in is by password.
 */

import type { FirebaseWebConfig } from "@/types/api";

export class GoogleSignInCancelled extends Error {}

const CANCELLED = new Set([
  "auth/popup-closed-by-user",
  "auth/cancelled-popup-request",
  "auth/user-cancelled",
]);

export async function googleIdToken(config: FirebaseWebConfig): Promise<string> {
  const [{ initializeApp, getApps }, auth] = await Promise.all([
    import("firebase/app"),
    import("firebase/auth"),
  ]);
  const app = getApps()[0] ?? initializeApp(config);
  const firebaseAuth = auth.getAuth(app);
  // The server session is what keeps someone signed in, not Firebase's own.
  await auth.setPersistence(firebaseAuth, auth.inMemoryPersistence);

  const provider = new auth.GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });
  try {
    const result = await auth.signInWithPopup(firebaseAuth, provider);
    return await result.user.getIdToken();
  } catch (error) {
    const code = (error as { code?: string }).code ?? "";
    if (CANCELLED.has(code)) throw new GoogleSignInCancelled(code);
    throw error;
  } finally {
    void auth.signOut(firebaseAuth);
  }
}

/**
 * Wording server errors in the interface language.
 *
 * The server explains itself in English. The explanations a person is likely
 * to meet are matched here and shown translated; anything else is shown as
 * the server wrote it, which is still more useful than a generic failure.
 */

import { ApiError } from "@/api/client";
import type { MessageKey, Params } from "./index";

const BY_CODE: Record<string, MessageKey> = {
  DUPLICATE: "error.duplicateName",
  TOO_MANY_REQUESTS: "error.tooManyAttempts",
  OLD_EXCEL: "error.oldExcel",
  UNSUPPORTED_FILE: "error.unsupportedFile",
  UNREADABLE_FILE: "error.unreadableFile",
  TOO_MANY_ROWS: "error.tooManyRows",
  FILE_TOO_LARGE: "error.fileTooLarge",
};

const BY_MESSAGE: Record<string, MessageKey> = {
  "Invalid email or password": "error.invalidLogin",
  "Account is temporarily locked": "error.accountLocked",
  "Password must be at least 12 characters long": "error.passwordTooShort",
  "Incorrect setup code": "error.setupCode",
  "Setup has already been completed": "error.setupDone",
  "Session expired or revoked": "error.sessionExpired",
  "This is the project's only administrator; make someone else one first": "error.lastAdmin",
  "This invite link is not valid any more": "invite.invalid",
  "An account already exists for that email address": "error.emailTaken",
  "Division still has people assigned to it": "error.divisionInUse",
  "Level is still referenced by a person's skill or a job requirement": "error.levelInUse",
  "End date must not precede start date": "error.dateOrder",
  "You may only request time off for yourself": "error.ownTimeOffOnly",
  "This account is not linked to a person record": "error.notLinked",
  "Incorrect or expired reset code": "error.resetCode",
  "No account uses that email address": "error.noSuchEmail",
};

export function errorText(
  error: unknown,
  t: (key: MessageKey, params?: Params) => string,
): string {
  if (error instanceof ApiError) {
    const key = BY_CODE[error.code] ?? BY_MESSAGE[error.message];
    if (key) return t(key);
    if (error.message) return error.message;
  }
  return t("error.generic");
}

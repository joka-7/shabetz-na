/**
 * Each member's end-to-end encryption key pair (docs/E2EE-DESIGN.md §2, §4.1, §4.7).
 *
 * The secret key is generated here and never leaves the browser in the clear.
 * What the server stores is the public key plus the secret key wrapped twice:
 * once under a key derived from the member's passphrase (Argon2id), once under
 * their recovery code. Either one unwraps it on a new device.
 *
 * Every function takes the libsodium instance it should use, so tests and the
 * app share one loaded copy and nothing here reaches for a global.
 */

import type sodiumModule from "libsodium-wrappers-sumo";

export type Sodium = typeof sodiumModule;

/** What the server stores for an account (the shape of `/api/keys/me`). */
export interface MemberKeyRecord {
  public_key: string;
  wrapped_sk_passphrase: string;
  wrapped_sk_recovery: string;
  kdf_salt: string;
  kdf_opslimit: number;
  kdf_memlimit: number;
}

/** The wrapped copies alone, for changing the passphrase or recovery code. */
export type MemberKeyWraps = Omit<MemberKeyRecord, "public_key">;

/** Argon2id cost. The server accepts 2–10 passes and 64 MiB–1 GiB. */
export interface KdfCost {
  opslimit: number;
  memlimit: number;
}

/** Three passes over 64 MiB: about a second on a phone, and inside the server's bounds. */
export const DEFAULT_KDF_COST: KdfCost = { opslimit: 3, memlimit: 64 * 1024 * 1024 };

/**
 * The most a stored record may ask this device to spend. A record from the
 * server is not trusted to be sane: a huge memory cost would crash a phone tab.
 */
const MAX_KDF_COST: KdfCost = { opslimit: 10, memlimit: 256 * 1024 * 1024 };

/** Shortest passphrase accepted; Argon2id slows guessing, it cannot fix a short secret. */
export const MIN_PASSPHRASE_LENGTH = 12;

/** Raised when a passphrase or recovery code does not open the stored key. */
export class WrongSecretError extends Error {
  constructor() {
    super("That passphrase or recovery code does not open this key");
    this.name = "WrongSecretError";
  }
}

/** Raised when an unwrapped key does not match the account's public key. */
export class KeyMismatchError extends Error {
  constructor() {
    super("The stored key does not match this account's public key");
    this.name = "KeyMismatchError";
  }
}

const KEY_BYTES = 32;
const RECOVERY_BYTES = 15;
// Crockford's base32: no I, L, O or U, so a code copied by hand is unambiguous.
const CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
const RECOVERY_GROUP = 4;

/** A new key pair, ready to upload, plus what the member must keep. */
export interface NewMemberKeys {
  record: MemberKeyRecord;
  secretKey: Uint8Array;
  /** 24 characters in six groups of four. Shown once; never sent to the server. */
  recoveryCode: string;
}

/**
 * Generates a key pair and wraps its secret key under the passphrase and a
 * fresh recovery code.
 *
 * @throws {RangeError} if the passphrase is shorter than {@link MIN_PASSPHRASE_LENGTH}.
 */
export function createMemberKeys(
  sodium: Sodium,
  passphrase: string,
  cost: KdfCost = DEFAULT_KDF_COST,
): NewMemberKeys {
  const pair = sodium.crypto_box_keypair();
  const recoveryBytes = sodium.randombytes_buf(RECOVERY_BYTES);
  const record: MemberKeyRecord = {
    public_key: sodium.to_base64(pair.publicKey),
    wrapped_sk_recovery: wrap(sodium, pair.privateKey, recoveryKey(sodium, recoveryBytes)),
    ...passphraseWrap(sodium, pair.privateKey, passphrase, cost),
  };
  return {
    record,
    secretKey: pair.privateKey,
    recoveryCode: formatRecoveryCode(recoveryBytes),
  };
}

/**
 * A new passphrase wrap of the same secret key. The recovery-code wrap is left
 * as it is, so the code the member wrote down keeps working, and the public
 * key and every project key sealed to it stay valid.
 */
export function rewrapPassphrase(
  sodium: Sodium,
  secretKey: Uint8Array,
  passphrase: string,
  current: MemberKeyRecord,
  cost: KdfCost = DEFAULT_KDF_COST,
): MemberKeyWraps {
  return {
    wrapped_sk_recovery: current.wrapped_sk_recovery,
    ...passphraseWrap(sodium, secretKey, passphrase, cost),
  };
}

/**
 * Opens the stored key with the passphrase.
 *
 * @throws {WrongSecretError} if the passphrase is wrong.
 * @throws {KeyMismatchError} if the result is not this account's key.
 */
export function unlockWithPassphrase(
  sodium: Sodium,
  record: MemberKeyRecord,
  passphrase: string,
): Uint8Array {
  if (record.kdf_opslimit > MAX_KDF_COST.opslimit || record.kdf_memlimit > MAX_KDF_COST.memlimit) {
    throw new KeyMismatchError();
  }
  const key = sodium.crypto_pwhash(
    KEY_BYTES,
    passphrase,
    sodium.from_base64(record.kdf_salt),
    record.kdf_opslimit,
    record.kdf_memlimit,
    sodium.crypto_pwhash_ALG_ARGON2ID13,
  );
  return checked(sodium, record, unwrap(sodium, record.wrapped_sk_passphrase, key));
}

/**
 * Opens the stored key with the recovery code. Spaces, dashes and letter case
 * are ignored, and the letters people confuse with digits are read as digits.
 *
 * @throws {WrongSecretError} if the code is malformed or wrong.
 * @throws {KeyMismatchError} if the result is not this account's key.
 */
export function unlockWithRecoveryCode(
  sodium: Sodium,
  record: MemberKeyRecord,
  code: string,
): Uint8Array {
  const bytes = parseRecoveryCode(code);
  if (bytes === null) throw new WrongSecretError();
  return checked(
    sodium,
    record,
    unwrap(sodium, record.wrapped_sk_recovery, recoveryKey(sodium, bytes)),
  );
}

/** `ABCD-EFGH-…` from the code's 15 bytes (120 bits, 24 base32 characters). */
export function formatRecoveryCode(bytes: Uint8Array): string {
  let bits = 0;
  let value = 0;
  let out = "";
  for (const byte of bytes) {
    value = ((value << 8) | byte) & 0xffff;
    bits += 8;
    while (bits >= 5) {
      out += CROCKFORD[(value >>> (bits - 5)) & 31];
      bits -= 5;
    }
  }
  const groups = out.match(new RegExp(`.{1,${RECOVERY_GROUP}}`, "g")) ?? [];
  return groups.join("-");
}

/** The code's bytes, or null if it is not 24 Crockford characters. */
export function parseRecoveryCode(code: string): Uint8Array | null {
  const normalised = code
    .toUpperCase()
    .replace(/[\s-]/g, "")
    .replace(/O/g, "0")
    .replace(/[IL]/g, "1");
  if (normalised.length !== (RECOVERY_BYTES * 8) / 5) return null;
  const bytes = new Uint8Array(RECOVERY_BYTES);
  let bits = 0;
  let value = 0;
  let index = 0;
  for (const char of normalised) {
    const digit = CROCKFORD.indexOf(char);
    if (digit === -1) return null;
    value = ((value << 5) | digit) & 0xffff;
    bits += 5;
    if (bits >= 8) {
      bytes[index++] = (value >>> (bits - 8)) & 0xff;
      bits -= 8;
    }
  }
  return bytes;
}

function passphraseWrap(
  sodium: Sodium,
  secretKey: Uint8Array,
  passphrase: string,
  cost: KdfCost,
): Pick<MemberKeyRecord, "wrapped_sk_passphrase" | "kdf_salt" | "kdf_opslimit" | "kdf_memlimit"> {
  if (passphrase.length < MIN_PASSPHRASE_LENGTH) {
    throw new RangeError(`A passphrase needs at least ${MIN_PASSPHRASE_LENGTH} characters`);
  }
  const salt = sodium.randombytes_buf(sodium.crypto_pwhash_SALTBYTES);
  const key = sodium.crypto_pwhash(
    KEY_BYTES,
    passphrase,
    salt,
    cost.opslimit,
    cost.memlimit,
    sodium.crypto_pwhash_ALG_ARGON2ID13,
  );
  return {
    wrapped_sk_passphrase: wrap(sodium, secretKey, key),
    kdf_salt: sodium.to_base64(salt),
    kdf_opslimit: cost.opslimit,
    kdf_memlimit: cost.memlimit,
  };
}

/**
 * The recovery code is 120 random bits, so a fast hash is enough to turn it
 * into a key; Argon2id is for secrets a person chose.
 */
function recoveryKey(sodium: Sodium, bytes: Uint8Array): Uint8Array {
  return sodium.crypto_generichash(KEY_BYTES, bytes, null);
}

/** `nonce ‖ secretbox(secretKey)`, base64 — 72 bytes, the size the server checks. */
function wrap(sodium: Sodium, secretKey: Uint8Array, key: Uint8Array): string {
  const nonce = sodium.randombytes_buf(sodium.crypto_secretbox_NONCEBYTES);
  const sealed = sodium.crypto_secretbox_easy(secretKey, nonce, key);
  const out = new Uint8Array(nonce.length + sealed.length);
  out.set(nonce);
  out.set(sealed, nonce.length);
  return sodium.to_base64(out);
}

function unwrap(sodium: Sodium, wrapped: string, key: Uint8Array): Uint8Array {
  const bytes = sodium.from_base64(wrapped);
  const nonce = bytes.subarray(0, sodium.crypto_secretbox_NONCEBYTES);
  const sealed = bytes.subarray(sodium.crypto_secretbox_NONCEBYTES);
  try {
    return sodium.crypto_secretbox_open_easy(sealed, nonce, key);
  } catch {
    // libsodium throws a bare Error on a failed MAC; that is the wrong-secret case.
    throw new WrongSecretError();
  }
}

function checked(sodium: Sodium, record: MemberKeyRecord, secretKey: Uint8Array): Uint8Array {
  const derived = sodium.crypto_scalarmult_base(secretKey);
  if (!sodium.memcmp(derived, sodium.from_base64(record.public_key))) {
    throw new KeyMismatchError();
  }
  return secretKey;
}

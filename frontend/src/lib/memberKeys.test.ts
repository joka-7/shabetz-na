import sodium from "libsodium-wrappers-sumo";
import { beforeAll, describe, expect, it } from "vitest";
import {
  KeyMismatchError,
  WrongSecretError,
  createMemberKeys,
  formatRecoveryCode,
  parseRecoveryCode,
  rewrapPassphrase,
  unlockWithPassphrase,
  unlockWithRecoveryCode,
  type KdfCost,
} from "./memberKeys";

// The cheapest cost the server accepts, so the suite stays quick.
const CHEAP: KdfCost = { opslimit: 2, memlimit: 64 * 1024 * 1024 };
const PASSPHRASE = "correct horse battery";

beforeAll(async () => {
  await sodium.ready;
});

const decodedLength = (value: string) => sodium.from_base64(value).length;

describe("createMemberKeys", () => {
  it("produces a record of exactly the sizes the server checks", () => {
    const { record, recoveryCode } = createMemberKeys(sodium, PASSPHRASE, CHEAP);

    expect({
      publicKey: decodedLength(record.public_key),
      wrappedPassphrase: decodedLength(record.wrapped_sk_passphrase),
      wrappedRecovery: decodedLength(record.wrapped_sk_recovery),
      salt: decodedLength(record.kdf_salt),
      cost: [record.kdf_opslimit, record.kdf_memlimit],
      encodingIsUnpaddedUrlSafe: /^[A-Za-z0-9_-]+$/.test(record.wrapped_sk_passphrase),
      recoveryCodeShape: /^([0-9A-HJKMNP-TV-Z]{4}-){5}[0-9A-HJKMNP-TV-Z]{4}$/.test(recoveryCode),
    }).toEqual({
      publicKey: 32,
      wrappedPassphrase: 72,
      wrappedRecovery: 72,
      salt: 16,
      cost: [CHEAP.opslimit, CHEAP.memlimit],
      encodingIsUnpaddedUrlSafe: true,
      recoveryCodeShape: true,
    });
  });

  it("refuses a short passphrase", () => {
    expect(() => createMemberKeys(sodium, "too short", CHEAP)).toThrow(RangeError);
  });
});

describe("unlockWithPassphrase", () => {
  it.each([
    ["the right passphrase opens the key", PASSPHRASE, null],
    ["a wrong passphrase is refused", "not the passphrase", WrongSecretError],
  ])("%s", (_label, attempt, error) => {
    const { record, secretKey } = createMemberKeys(sodium, PASSPHRASE, CHEAP);

    const act = () => unlockWithPassphrase(sodium, record, attempt);

    if (error) expect(act).toThrow(error);
    else expect(act()).toEqual(secretKey);
  });

  it("refuses a key that does not belong to the record's public key", () => {
    const mine = createMemberKeys(sodium, PASSPHRASE, CHEAP);
    const theirs = createMemberKeys(sodium, PASSPHRASE, CHEAP);
    const swapped = { ...mine.record, public_key: theirs.record.public_key };

    expect(() => unlockWithPassphrase(sodium, swapped, PASSPHRASE)).toThrow(KeyMismatchError);
  });
});

describe("unlockWithRecoveryCode", () => {
  it.each([
    ["the code as shown", (code: string) => code],
    ["lower case without dashes", (code: string) => code.replace(/-/g, "").toLowerCase()],
    ["with spaces between groups", (code: string) => code.replace(/-/g, " ")],
  ])("opens the key with %s", (_label, typed) => {
    const { record, secretKey, recoveryCode } = createMemberKeys(sodium, PASSPHRASE, CHEAP);

    expect(unlockWithRecoveryCode(sodium, record, typed(recoveryCode))).toEqual(secretKey);
  });

  it.each([
    ["a malformed code", "ABCD"],
    ["another valid-looking code", "0000-0000-0000-0000-0000-0000"],
  ])("refuses %s", (_label, code) => {
    const { record } = createMemberKeys(sodium, PASSPHRASE, CHEAP);

    expect(() => unlockWithRecoveryCode(sodium, record, code)).toThrow(WrongSecretError);
  });
});

describe("rewrapPassphrase", () => {
  it("opens with the new passphrase and the old recovery code, not the old passphrase", () => {
    const original = createMemberKeys(sodium, PASSPHRASE, CHEAP);
    const wraps = rewrapPassphrase(sodium, original.secretKey, "a brand new passphrase", original.record, CHEAP);
    const updated = { ...original.record, ...wraps };

    expect({
      newPassphrase: unlockWithPassphrase(sodium, updated, "a brand new passphrase"),
      oldCode: unlockWithRecoveryCode(sodium, updated, original.recoveryCode),
    }).toEqual({ newPassphrase: original.secretKey, oldCode: original.secretKey });
    expect(() => unlockWithPassphrase(sodium, updated, PASSPHRASE)).toThrow(WrongSecretError);
  });
});

describe("unlockWithPassphrase cost limits", () => {
  it("refuses a record that asks for more memory than a phone can spare", () => {
    const { record } = createMemberKeys(sodium, PASSPHRASE, CHEAP);

    expect(() =>
      unlockWithPassphrase(sodium, { ...record, kdf_memlimit: 1024 * 1024 * 1024 }, PASSPHRASE),
    ).toThrow(KeyMismatchError);
  });
});

describe("formatRecoveryCode / parseRecoveryCode", () => {
  it.each([
    ["all zero bits", new Uint8Array(15)],
    ["all one bits", new Uint8Array(15).fill(0xff)],
    ["a mixed pattern", Uint8Array.from({ length: 15 }, (_, i) => (i * 37 + 11) & 0xff)],
  ])("round-trips %s", (_label, bytes) => {
    expect(parseRecoveryCode(formatRecoveryCode(bytes))).toEqual(bytes);
  });

  it.each([
    ["a known value", new Uint8Array(15).fill(0xff), "ZZZZ-ZZZZ-ZZZZ-ZZZZ-ZZZZ-ZZZZ"],
    ["zeros", new Uint8Array(15), "0000-0000-0000-0000-0000-0000"],
  ])("formats %s", (_label, bytes, expected) => {
    expect(formatRecoveryCode(bytes)).toBe(expected);
  });

  it.each([
    ["O and I and L read as digits", "OOOO-0000-0000-0000-0000-000I", "0000-0000-0000-0000-0000-0001"],
  ])("parses %s", (_label, typed, canonical) => {
    expect(parseRecoveryCode(typed)).toEqual(parseRecoveryCode(canonical));
  });

  it.each([["too short", "ABC"], ["a U, which is not in the alphabet", "UUUU-UUUU-UUUU-UUUU-UUUU-UUUU"]])(
    "rejects %s",
    (_label, typed) => {
      expect(parseRecoveryCode(typed)).toBeNull();
    },
  );
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import sodium from "libsodium-wrappers-sumo";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { MemberKeyProvider } from "@/hooks/useMemberKey";
import { I18nProvider } from "@/i18n";
import { createMemberKeys, unlockWithPassphrase, type MemberKeyRecord } from "@/lib/memberKeys";
import { EncryptionKeys } from "./EncryptionKeys";

// The server is the I/O boundary: a tiny in-memory stand-in for /api/keys/me.
const server = vi.hoisted(() => ({ stored: null as MemberKeyRecord | null, posts: 0 }));

vi.mock("@/api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/client")>();
  return {
    ...original,
    api: {
      get: async () => {
        if (!server.stored) throw new original.ApiError(404, "NOT_FOUND", "none");
        return server.stored;
      },
      post: async (_path: string, body: MemberKeyRecord) => {
        server.posts += 1;
        server.stored = body;
        return body;
      },
      put: async (_path: string, body: Partial<MemberKeyRecord>) => {
        server.stored = { ...(server.stored as MemberKeyRecord), ...body };
        return server.stored;
      },
    },
  };
});

vi.mock("@/hooks/useSession", () => ({
  useSession: () => ({ user: { id: 1 }, capabilities: { deployment: "server" } }),
}));

const PASSPHRASE = "correct horse battery";
const CHEAP = { opslimit: 2, memlimit: 64 * 1024 * 1024 };

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <I18nProvider>
      <QueryClientProvider client={client}>
        <MemberKeyProvider>
          <EncryptionKeys />
        </MemberKeyProvider>
      </QueryClientProvider>
    </I18nProvider>,
  );
}

function type(label: string | RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

beforeAll(async () => {
  await sodium.ready;
});

beforeEach(() => {
  server.stored = null;
  server.posts = 0;
});

describe("EncryptionKeys", () => {
  it("sets up a key only after the recovery code is confirmed, then shows it unlocked", async () => {
    renderSection();
    await screen.findByLabelText("Encryption passphrase");
    type("Encryption passphrase", PASSPHRASE);
    type("Encryption passphrase again", PASSPHRASE);
    fireEvent.click(screen.getByRole("button", { name: "Create my key" }));

    const code = (await screen.findByText(/^([0-9A-Z]{4}-){5}[0-9A-Z]{4}$/, {}, { timeout: 10_000 }))
      .textContent as string;
    expect(server.posts).toBe(0);
    type(/last four characters/, code.slice(-4));
    fireEvent.click(screen.getByRole("button", { name: "I saved it" }));

    expect(await screen.findByText(/Unlocked in this tab/)).toBeInTheDocument();
    expect(server.posts).toBe(1);
  });

  it.each([
    ["a wrong passphrase is refused", "not the passphrase", /does not open your key/],
    ["the right passphrase unlocks", PASSPHRASE, /Unlocked in this tab/],
  ])("%s", async (_label, attempt, outcome) => {
    server.stored = createMemberKeys(sodium, PASSPHRASE, CHEAP).record;
    renderSection();

    await screen.findByLabelText("Encryption passphrase");
    type("Encryption passphrase", attempt);
    fireEvent.click(screen.getByRole("button", { name: "Unlock in this tab" }));

    await waitFor(() => expect(screen.getByText(outcome)).toBeInTheDocument(), { timeout: 10_000 });
  });

  it("unlocks with the recovery code, and a passphrase change keeps that code working", async () => {
    const made = createMemberKeys(sodium, PASSPHRASE, CHEAP);
    server.stored = made.record;
    renderSection();

    fireEvent.click(await screen.findByRole("button", { name: "Use the recovery code instead" }));
    type("Recovery code", made.recoveryCode.toLowerCase());
    fireEvent.click(screen.getByRole("button", { name: "Unlock in this tab" }));
    fireEvent.click(await screen.findByRole("button", { name: "Change encryption passphrase" }, { timeout: 10_000 }));
    type("Encryption passphrase", "a brand new passphrase");
    type("Encryption passphrase again", "a brand new passphrase");
    fireEvent.click(screen.getByRole("button", { name: "Save the new encryption passphrase" }));

    await screen.findByText(/Unlocked in this tab/, {}, { timeout: 10_000 });
    expect(server.stored.wrapped_sk_recovery).toBe(made.record.wrapped_sk_recovery);
    expect(unlockWithPassphrase(sodium, server.stored, "a brand new passphrase")).toEqual(made.secretKey);
  });

  it("uploads only the public record, never the secret key or recovery code", async () => {
    renderSection();
    await screen.findByLabelText("Encryption passphrase");
    type("Encryption passphrase", PASSPHRASE);
    type("Encryption passphrase again", PASSPHRASE);
    fireEvent.click(screen.getByRole("button", { name: "Create my key" }));
    const code = (await screen.findByText(/^([0-9A-Z]{4}-){5}[0-9A-Z]{4}$/, {}, { timeout: 10_000 }))
      .textContent as string;
    type(/last four characters/, code.slice(-4));
    fireEvent.click(screen.getByRole("button", { name: "I saved it" }));
    await screen.findByText(/Unlocked in this tab/);

    const uploaded = server.stored as MemberKeyRecord;
    expect(Object.keys(uploaded).sort()).toEqual(
      ["kdf_memlimit", "kdf_opslimit", "kdf_salt", "public_key", "wrapped_sk_passphrase", "wrapped_sk_recovery"],
    );
    expect(JSON.stringify(uploaded)).not.toContain(code);
  });
});

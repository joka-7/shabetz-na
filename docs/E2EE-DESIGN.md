# Shabetz: end-to-end encryption — design (draft for approval)

Status: **design only, no code.** Nothing here is built until it is approved.

> **Already built, and a different guarantee:** encryption at rest
> ([PRIVACY.md](PRIVACY.md)) hides personal data from anyone with access to the
> *database alone*, using a key held by the application. This document is about
> the stronger goal of hiding it from the server as well, which that does not do.

Goal: the server (Render), the database (Neon) and whoever operates them hold
only **ciphertext** for schedule content. They keep the routing metadata needed
to deliver it: project ids, member ids, timestamps and sizes.

---

## 1. What this protects, and what it cannot

| Threat | Protected? |
| :-- | :-- |
| Someone reads a Neon backup or dump | **Yes**: only ciphertext and public keys are in it |
| A Render or Neon employee, or a leaked DB password, reads the tables | **Yes** |
| The operator (J) browses the database | **Yes** |
| The operator ships a modified JavaScript bundle that steals keys | **No**, not in a web app. Whoever serves the page's code can change it. See §1.1 |
| A member's own device is compromised | No (no E2EE system can) |
| A removed member keeps what they had already decrypted | No (inherent) |
| Metadata: how many people, how often schedules change, who requested something and when | No; it stays visible by design |

### 1.1 The web-app caveat (important)

In a browser, the code that does the encryption comes from a server. If the
party we're hiding from can change that code, they can make it send the keys
home. To reduce this:

1. Serve the frontend from **Vercel** and the API from **Render**: two
   separate operators, so changing the code needs access to the Vercel
   project.
2. Pin the build: publish the bundle hash for each release in the GitHub
   release notes, and add Subresource Integrity to `index.html`'s script tags.
3. For the strongest guarantee, use a **signed installed app** (the Windows
   desktop app, or a future Capacitor/mobile build), where the code doesn't
   change on every page load.

Without (3), Phase 2 protects against database leaks and casual operator
access, but **not** against a determined operator who also controls the
frontend deployment. This should be decided knowingly.

---

## 2. Keys

Library: **libsodium** (`libsodium-wrappers-sumo` in the browser,
`PyNaCl` on the server only for tests). No home-made crypto.

| Key | Type | Lives | Purpose |
| :-- | :-- | :-- | :-- |
| **Member key pair** `(pk_m, sk_m)` | X25519 (`crypto_box_keypair`) | `pk_m` on the server; `sk_m` only on the member's devices, and on the server only as `wrapped_sk` (below) | Receives wrapped project keys and sealed requests |
| **Device unlock key** | derived with Argon2id (`crypto_pwhash`) from a passphrase, *or* a random key kept in IndexedDB as a non-extractable WebCrypto key | the device | Encrypts `sk_m` at rest on the device and on the server (`wrapped_sk`) so a new device can sign in with the passphrase |
| **Recovery key** | 128-bit random, shown once as a 24-character code | printed or saved by the member | A second wrap of `sk_m` for when the passphrase is forgotten |
| **Project key** `K_p` (versioned) | 256-bit secretbox key (XChaCha20-Poly1305) | wrapped per member: `crypto_box_seal(K_p, pk_m)` | Encrypts all project content |
| **Schedule key** `K_s` | 256-bit, one per published schedule | wrapped with `K_p`; also placed in a share link's URL fragment | Lets a link open exactly one schedule |
| **Project inbox key pair** `(pk_in, sk_in)` | X25519 | `pk_in` public; `sk_in` encrypted with `K_p` | Staff seal time-off/swap requests to it; any manager can open them |

Why an inbox key pair instead of sealing to each manager: requests stay
readable when managers change, and staff only need one public key.

### New tables (server sees only ciphertext)

```
member_keys        (user_id, public_key, wrapped_sk_passphrase, wrapped_sk_recovery,
                    kdf_salt, kdf_params, created_at)
project_key_wraps  (project_id, member_id, key_version, sealed_key, created_at)
project_keys       (project_id, key_version, created_at, retired_at)
encrypted_blobs    (id, project_id, kind, key_version, nonce, ciphertext, created_at, updated_at, version)
```

`kind` covers: `config` (divisions, skills, levels, templates, jobs, settings),
`roster` (people), `draft`, `published`, `request`, `audit`.

---

## 3. What moves from the server to the browser

Today the server reads everything, so it does a lot of work that it can no
longer do once it can't read the data:

| Today on the server | Under E2EE |
| :-- | :-- |
| **Schedule generation** (`scheduling/greedy.py`, Python) | **In the manager's browser.** Either port the engine to TypeScript (about 600 lines including warnings and rotation; the existing 23 engine tests become the port's spec), or run the Python as-is with **Pyodide** (about 10 MB download, no port, slower first load). Recommendation: the TypeScript port. |
| Feasibility preflight (`setup/feasibility.py`) | Browser (port alongside the engine) |
| Edit conflict checks, suggestions, undo (`services/schedule_edit.py`) | Browser; the server stores the new encrypted blob with the existing optimistic `version` check |
| Swap validation ("is this shift yours", conflicts on approval) | Browser of the requester, then of the approving manager. The server can only check *membership and state transitions*, not content |
| Time-off vs published-schedule clash warning | Manager's browser |
| CSV/HTML/PDF export (WeasyPrint) | Browser: CSV and HTML directly; PDF via the existing print layout (`PrintGrid`) and the browser's "Save as PDF" |
| Excel import parsing (openpyxl) | Browser (SheetJS, or the existing paste path) |
| Publish email ("new schedule for …") | Stays, but **content-free**: "A new schedule was published — sign in to see it." Names and dates can't be in it |
| Audit log `before_json`/`after_json` | Encrypted blob of kind `audit`; the server keeps only who, when and the action verb |
| Staff "my shifts" filtering | Browser: staff decrypt the published schedule and filter locally. If staff must not see the whole schedule, see §5 |

What stays on the server unchanged: accounts and sign-in, the allowlist
(Phase 1), sessions, CSRF, projects, membership and roles, invites, throttling,
and blob storage with versioning.

---

## 4. Flows

### 4.1 First sign-in after the feature ships
1. The browser generates `(pk_m, sk_m)` and asks for a passphrase (or offers device-only storage).
2. It shows a recovery code once and makes the member confirm two of its characters.
3. It uploads `pk_m`, `wrapped_sk_passphrase` and `wrapped_sk_recovery`.

### 4.2 Creating a project
The creator's browser generates `K_p` v1 and `(pk_in, sk_in)`, stores
`seal(K_p, pk_creator)`, and stores `sk_in` encrypted under `K_p`.

### 4.3 Adding a member (invite link)
- The invite link becomes `/invite/<token>#k=<invite secret>`. The fragment is never sent to the server.
- The admin's browser stores `secretbox(K_p, invite_secret)` alongside the invite.
- On accept, the new member's browser opens it with the fragment secret and immediately stores `seal(K_p, pk_new)`.
- A single-use invite then deletes its wrapped copy. A multi-use staff link keeps it until it expires or is revoked.
- Without a fragment (for example, a link retyped by hand), the membership is created as **pending key**. The next time any admin opens the project, their browser wraps `K_p` for the new member automatically.

### 4.4 Removing a member (re-wrap / rotation)
1. The admin's browser generates `K_p` v(n+1).
2. It re-encrypts the *current* blobs (config, roster, the published schedule, open requests) under the new key. Old drafts and audit entries can stay on v(n), or be re-encrypted in the background.
3. It seals v(n+1) for each remaining member and retires v(n).
4. A removed member can no longer read anything new. Anything they already downloaded can't be taken back.

### 4.5 Publishing
1. The manager's browser creates `K_s` and stores the schedule as `secretbox(schedule, K_s)` with `K_s` wrapped under `K_p`.
2. Members open it through `K_p`.
3. **Share link** (no account needed): `/s/<schedule id>#k=<K_s>`. Anyone holding the link can read *that schedule only*, and nothing else in the project. Revoking it means re-publishing with a new `K_s`.

### 4.6 Time off and swaps
1. Staff seal the request body (dates, reason, shift, note) to `pk_in` with `crypto_box_seal`.
2. The server stores `(project_id, requester member id, kind, state, created_at, ciphertext)`, so it can still enforce the state machine: who may cancel, accept or decide.
3. A manager's browser opens the request with `sk_in`, checks it against the decrypted schedule, and records the decision. A decision note is encrypted under `K_p`.

### 4.7 Key recovery
| Lost | Way back |
| :-- | :-- |
| Passphrase | Recovery code → unwrap `sk_m` → set a new passphrase |
| Passphrase **and** recovery code | Generate a new member key pair. Any other admin's browser re-wraps `K_p` for it (the same path as a pending-key member). With no other admin, **the project's data is unrecoverable by design.** So the UI should insist on two admins (the last-admin guard already exists) |
| The only admin's device, passphrase and code | Data unrecoverable. This must be said plainly in onboarding |

### 4.8 Migrating today's plaintext data
After the upgrade, the first admin to sign in to a project:
1. Creates `K_p`.
2. Downloads the existing plaintext through the current endpoints.
3. Encrypts it and uploads the blobs.
4. Confirms. The server then **deletes** the plaintext rows, and the old endpoints for that project return 410.

Projects not yet migrated keep working as today. A banner says which projects are still unencrypted.

---

## 5. Open decisions for you

1. **Do staff see the whole published schedule?** Today the server gives staff only their own shifts. Under E2EE, the simplest model hands staff `K_s`, which opens the whole schedule. Keeping today's privacy needs a per-person extract sealed to each member's `pk_m` at publish time. That's more work for the manager's browser, but straightforward. *Recommendation: per-person extracts, plus an optional whole-schedule share link.*
2. **Engine: TypeScript port or Pyodide?** *Recommendation: TypeScript.*
3. **Passphrase or device-only keys?** Device-only is friendlier but makes a second device depend on the recovery code. *Recommendation: passphrase, with the recovery code as backup.*
4. **Is §1.1's caveat acceptable for the web app,** or should E2EE be offered only in an installed app?
5. **Which scope:** "full" (A) or "published schedules and requests only" (B)? See §6.

---

## 6. Estimates

Sessions are the same unit as in your plan (about one focused working session each).

### Scope A — full: config, roster, drafts, published schedules, requests and audit all encrypted

| Piece | Sessions |
| :-- | --: |
| libsodium wiring, member key pairs, passphrase and recovery code, the tables above, unlock UI | 1 |
| Project keys, wrapping, pending-key members, invite fragment flow | 1 |
| Port the engine, feasibility and warnings to TypeScript, with the existing tests ported as the spec | 2 |
| Move editing, conflicts, suggestions, undo and audit to the browser over encrypted blobs (with the `version` check) | 1.5 |
| Publish with per-person extracts and share links | 1 |
| Sealed time-off and swap requests and the inbox key; manager decisions | 1 |
| Member removal and key rotation | 0.5 |
| Client-side exports and import parsing | 0.5 |
| Migrating existing projects | 0.5 |
| Tests (crypto round-trips, a "the server never sees plaintext" test that scans every request body), a security review pass, docs | 1 |
| **Total** | **about 10** |

### Scope B — what fits your 4–6 sessions: the operator can't read published schedules or requests

Config, roster and drafts stay readable by the server. That means
generation, editing and validation stay server-side as they are today. Only
what is **published to staff** and what **staff send** is encrypted.

| Piece | Sessions |
| :-- | --: |
| Member key pairs, passphrase and recovery code | 1 |
| Project key and invite fragment flow (can be shared with scope A later) | 1 |
| Publish: the manager's browser encrypts per-person extracts and the share link; the server deletes its plaintext copy of the *published* run after publishing | 1 |
| Sealed requests and inbox key; the manager's browser does the clash and conflict checks | 1 |
| Rotation on member removal, tests, docs | 1 |
| **Total** | **about 5** |

Under B the server still sees the roster and drafts while the manager works.
It never stores what staff see or ask for. B is a sound first step, and
everything it builds is reused by A.

---

## 7. Alternative (from your plan)

For a manager who never shares online, the **Windows desktop app**
(`src/shabetz/desktop.py`) already keeps everything on one computer, with no
server and no operator. It now also backs up its database on every launch
(`%LOCALAPPDATA%\Shabetz\backups`, the newest 10 kept).

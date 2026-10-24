# Privacy: who can see people's data

**Short answer.** With `SHABETZ_DATA_KEY` set, names, emails, notes and schedules
are stored **encrypted** in the database. Someone who has access to the database
only — hosting staff, a leaked connection string, a stolen backup — sees
ciphertext. Someone who controls the *application's* settings (where the key is)
can still read everything, because the app has to.

If that is not enough, see [E2EE-DESIGN.md](E2EE-DESIGN.md): end-to-end
encryption would hide the data from the server too, at a much higher cost.

## Who can see what

| Who | Without a key | With `SHABETZ_DATA_KEY` |
| :-- | :-- | :-- |
| Someone with **database access only** (Neon console or staff, a leaked `SHABETZ_DATABASE_URL`, a dump or backup) | Everything | Ciphertext for personal data. Still visible: see "Not encrypted" below |
| Whoever controls the **Render settings** (they can read the key) | Everything | **Everything**: the app decrypts for them |
| Someone who gets **both** the database and the key | Everything | Everything |
| People signing in | What their role allows | What their role allows (nothing changes) |

Encryption at rest does not change what any signed-in person can see; roles still
decide that (staff see their own shifts, and so on).

## What is encrypted

Personal data, in every table:

- **Accounts:** email address and full name; the browser/device text of each sign-in.
- **People:** full name and any reference number.
- **Schedules:** the whole generated schedule, which has everyone's name in it.
- **Time off:** the reason and the reviewer's note.
- **Shift swaps:** the request note and the decision note.
- **Attendance:** the note on each mark.
- **Activity log:** what each change replaced and what it left (it contains names).

Each value is sealed with AES-256-GCM, a fresh random nonce every time, and the
column's name as authenticated data, so a value copied into another column fails
to open and any change to it is detected.

Signing in by email still works: the app keeps a keyed fingerprint of each
address (an HMAC), so an account can be found without storing the address in the
clear. Without the key the fingerprint cannot be computed, and guessing addresses
cannot reproduce it.

## What is **not** encrypted

Anyone with database access can still see the *shape* of the data:

- That accounts and people exist, how many, and when they were created.
- Dates and times: when time off starts and ends, which days have attendance
  marks, the date range of each schedule, when someone last signed in.
- Ids and states: which person id is away on which date, present or absent,
  approved or pending, who holds which role in which project.
- Configuration names: division, skill, proficiency level, shift window and job
  names, project (organisation) names and settings.
- Password hashes (Argon2, so not reversible) and hashed session ids.

Because people's names are encrypted, those ids cannot be tied back to a name
without the key.

## Turning it on

1. Generate a key and **store it somewhere safe** (a password manager):

   ```
   uv run shabetz generate-data-key
   ```

   Any random string of at least 32 characters works.

2. On Render: your service → **Environment** → add `SHABETZ_DATA_KEY` with the
   key → **Save, rebuild, and deploy**.

3. On start-up the server encrypts the existing data before it serves anything.
   The log says so: `Personal data is encrypted (key …); encrypted N existing rows.`
   New data is encrypted as it is written. Until the key is set, nothing changes.

Self-hosted: put `SHABETZ_DATA_KEY=…` in the environment and restart.
`shabetz data-status` shows whether a key is configured and how many rows are
still waiting.

### Do not lose the key

**If the key is lost, the encrypted data can never be read again.** There is no
recovery, by design.

- Keep a copy outside Render.
- If you delete and recreate the service, give it the **same** key.
- Backups made with `shabetz backup` (or the host's own) contain ciphertext, so a
  restore needs the same key as well. That is also what makes a leaked backup
  harmless.
- With a key configured the server refuses to start if the key is removed while
  encrypted data remains, rather than coming up and failing on every page.

## Changing the key (rotation)

1. Set `SHABETZ_OLD_DATA_KEYS` to the current key, and `SHABETZ_DATA_KEY` to a
   new one. Deploy.
2. On start-up the server re-encrypts everything under the new key. Signing in
   keeps working throughout.
3. When the log shows no rows left, remove `SHABETZ_OLD_DATA_KEYS`.

## Turning it off

Set the key, run `shabetz decrypt-data`, then remove `SHABETZ_DATA_KEY`. Going
back to an older database version (a migration downgrade) is refused while any
data is still encrypted.

## The desktop app

The Windows app keeps its data in a file in the owner's own folder, on their own
computer, so there is no separate database administrator to hide it from. It does
encrypt that file, and encryption is not supported there. (Anyone who can open the
folder can read it, as with any document there.)

## Other places data goes

Encryption at rest covers the database only. Also worth knowing:

- **Email notifications** (if you set SMTP) contain what you send; the app sends
  only "a new schedule was published".
- **Calendar feed addresses** let anyone holding the address read that person's
  shifts; treat them like a password. They can be replaced or switched off in
  Settings.
- **Google sign-in** means Google sees that a person signed in.
- **Render and Vercel** can see traffic as it passes through, and Render's
  environment holds the key.
- **Request logs.** The app itself logs no names or emails. But a host's request
  logs record the address of every request, and two kinds of address are secret
  links: calendar feeds (`/api/calendar/…`) and invite links (`/api/invites/…`).
  Anyone who can read your host's logs can read those. Replace a calendar address
  in Settings if it may have been exposed; invite links expire and rights-granting
  ones work once.

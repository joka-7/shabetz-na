# Installing Shabetz on Windows

No technical knowledge needed, and no administrator rights.

## 1. Download

Download **`Shabetz-Setup-<version>.exe`** from the project's Releases page.

## 2. Install

Double-click the file you downloaded.

**Windows will probably warn you first.** You will see a blue box saying
*"Windows protected your PC"*. This appears for any program that has not paid
for a code-signing certificate — it does not mean something is wrong.

1. Click **More info**.
2. Click **Run anyway**.

Then follow the installer. It will offer to put a Shabetz icon on your desktop.

## 3. First start

Shabetz opens in its own window. The first screen asks you to create the
administrator account — this is you. Choose a password of at least 12
characters and keep it somewhere safe; this screen only ever appears once.

A setup guide then walks you through your organisation: your divisions, shift
times, skills, jobs and people. You can change any of it later under
**Configuration**.

## Everyday use

- Open Shabetz from the desktop icon or the Start menu.
- **Close the window to stop it.** Nothing keeps running afterwards.
- Opening it again while it is running opens a second window onto the same
  app. It never starts a second copy, so your data stays in one place.

## Where your data is

Everything is stored on this computer, in:

```
%LOCALAPPDATA%\Shabetz
```

(Paste that into the File Explorer address bar to open it.)

| File | What it is |
| :-- | :-- |
| `shabetz.db` | All your data. **Back this file up.** |
| `secret.key` | Keeps you signed in between starts. |
| `shabetz.log` | A record of what happened — send it if you report a problem. |

Uninstalling or upgrading Shabetz never touches this folder.

**To back up:** close Shabetz, then copy `shabetz.db` somewhere safe (a USB
stick, a cloud folder). **To restore:** close Shabetz and put the copy back.

## If something goes wrong

- **It opens in a web browser instead of its own window.** Your computer is
  missing Microsoft's WebView2 component. Everything still works. To get the
  window back, install *Microsoft Edge WebView2 Runtime* from Microsoft's
  website.
- **Nothing happens when I open it.** Look in `shabetz.log` (see above) and
  send the last lines to whoever supports you.
- **I forgot the administrator password.** If another administrator exists,
  they can set a new one under Configuration → Accounts. If you were the only
  one, the data can only be recovered by someone technical editing the
  database, so create a second administrator account once you are set up.

## The desktop app and the website are separate

This program keeps its data on this one computer. If your organisation also
runs the Shabetz website so people can sign in from anywhere, that has its own
separate data — changes in one do not appear in the other.

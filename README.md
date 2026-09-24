# shabetz-na

Personnel shift scheduling, driven entirely by configuration.

There are no built-in division names, no fixed number of shifts, no fixed shift
times, and no fixed proficiency ladder. An administrator defines all of it
through a first-run wizard and can change any of it afterwards.

## What it does

Given a roster and a set of jobs, it produces a shift schedule over any date
range that respects:

- **Division rotation** — duty passes between divisions in the order you set them, for as many days at a time as you choose.
- **Rest between shifts** — a configurable minimum, and the *only* limit on how often someone works; there is no separate shifts-per-day cap.
- **Head count and skills** — per job, with requirements that apply either to everyone on a shift or to "at least N" of them, which is how mandatory roles are expressed.
- **Availability** — working days per person, plus approved time off.

Schedules export to CSV, HTML and PDF, and staff can see their own shifts and
request time off.

The interface is in **English and Hebrew** (right to left), switchable from any
screen. A roster does not have to be typed in: people can be imported from an
Excel or CSV file, or pasted straight out of a spreadsheet, with a preview of
every row before anything is saved. Divisions, skills, levels and shift windows
accept a pasted list the same way.

## Two ways to run it

| | For | Data |
| :-- | :-- | :-- |
| **Windows desktop app** | One computer, no technical setup. Download an installer, double-click, done. See [docs/INSTALL-WINDOWS.md](docs/INSTALL-WINDOWS.md). | SQLite, in the user's own folder |
| **Hosted website** | People signing in from anywhere with their own accounts. On Render in about 15 minutes: [docs/RENDER.md](docs/RENDER.md). Any other host: [docs/HOSTING.md](docs/HOSTING.md). | PostgreSQL or MySQL |

Both are the same application. The installer is built by GitHub Actions on
Windows (`.github/workflows/desktop.yml`); pushing a `v*` tag publishes it as a
release.

## Quick start (development)

```bash
make install                       # backend and frontend dependencies
cp .env.example .env               # then edit it
make db-up && make migrate         # MySQL 8 via Docker, then schema
make seed                          # optional: an example configuration
make dev                           # API on :8000, UI on :5173
```

Open http://localhost:5173. With an empty database the first screen creates the
administrator account; that route closes permanently once an account exists.

`make help` lists everything else.

## Feasibility checking

An administrator who can configure anything can configure something
impossible, so the system says so before generating a schedule full of
unexplained gaps.

The number that matters is not the busiest moment but the count of *distinct*
people a duty day needs. When the rest window stops one crew covering two
windows, their head counts add rather than overlap. For three round-the-clock
jobs at an eight-hour rest window:

| | |
| :-- | --: |
| person-shifts per day | 19 |
| busiest single moment | 7 |
| **distinct people needed per day** | **13** |

A division of 15 therefore has two people of slack — and at a five-day working
week only about 10.7 are available on a given day, below the floor. The
preflight reports this per division, names the specific shortfall, and suggests
what to change.

```bash
uv run shabetz feasibility
```

## Architecture

```
src/shabetz/
  domain/          pure dataclasses and enums; no ORM, no framework
  scheduling/      strategy interface + greedy scheduler + rotation
  setup/           feasibility preflight
  repositories/    maps configuration rows into domain objects
  services/        orchestration facade, settings
  db/              SQLAlchemy models and session
  auth/            passwords, sessions, roles
  exporters/       CSV, HTML, PDF from one template
  api/             FastAPI routers and schemas
frontend/src/
  features/        auth, setup wizard, config, dashboard, time off, export
  lib/schedule.ts  derived dashboard values (pure, unit-tested)
```

`domain/` and `scheduling/` import nothing from SQLAlchemy or FastAPI, which is
what keeps the engine testable without a database.

### Roles

| Role | May |
| :-- | :-- |
| `ADMIN` | change any configuration, manage users, everything below |
| `SCHEDULER` | generate schedules, review time off, read configuration |
| `STAFF` | see own shifts, export own schedule, request own time off |

Authorization is enforced by API dependencies and by query scoping, not by
frontend routing: a staff user who edits an id in a URL gets their own records,
not someone else's.

### Notes on MySQL

Set from the first migration, because retrofitting them onto a populated
database is painful:

- `utf8mb4` throughout — MySQL's `utf8` is a three-byte subset that mangles anything outside the Basic Multilingual Plane.
- Bounded `VARCHAR` on indexed columns, inside InnoDB's 3072-byte key limit.
- `DATETIME(6)` rather than `TIMESTAMP`, which is 32-bit and stops working in 2038.
- `LONGBLOB` for stored schedule payloads, with `max_allowed_packet` raised to match.

MySQL has no transactional DDL, so each migration makes one logical change and
carries a working `downgrade()`.

### PDF export

PDF rendering uses WeasyPrint, which needs system Pango and cairo. It is an
optional extra and is probed rather than imported at startup: where it is
missing, CSV and HTML keep working and the PDF button is not offered.

```bash
uv sync --extra pdf   # plus the system packages for your platform
```

## Testing

```bash
make test    # pytest + vitest
make lint    # ruff, mypy, tsc
make check   # both
```

The engine tests pin six behaviours that are easy to regress: date iteration
terminating, shift slots deriving from configured templates, scarce work being
staffed before general pools drain the roster, named roles being filled before
general head count, availability being seeded so an hour-zero shift is
reachable, and understaffing being reported rather than swallowed.

The unit and API tests run on SQLite. CI separately applies and rolls back the
migrations, seeds a configuration and generates a schedule against a real
MySQL 8 and a real PostgreSQL 16, and runs the API tests on PostgreSQL too
(`SHABETZ_TEST_DATABASE_URL`), because dialect differences would otherwise
pass locally and fail in production. It also builds and smoke-tests
the server image and the Windows executable.

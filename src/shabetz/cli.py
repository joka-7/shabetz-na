"""Command line entry points."""

from __future__ import annotations

import os
import random
import secrets
from datetime import date, timedelta

import typer
from sqlalchemy import select

from .auth.service import bootstrap_first_admin, setup_is_complete
from .db import models as orm
from .db.session import session_scope
from .domain.enums import DivisionPolicy, ProjectRole
from .services.orchestration import JobOrchestrationService
from .services.settings_service import SchedulingSettings, save_settings

app = typer.Typer(help="Shabetz scheduling administration.", no_args_is_help=True)

SEED = 20261001

# No 0/O or 1/I/L: the code is read from a log and typed by a person.
SETUP_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _choose_project(db, project: int | None) -> int:  # type: ignore[no-untyped-def]
    """The project a command acts on: the one named, or the only one there is."""
    if project is not None:
        if db.get(orm.Project, project) is None:
            typer.secho(f"No project {project}.", fg="red")
            raise typer.Exit(1)
        return project
    rows = db.execute(select(orm.Project.id, orm.Project.name).order_by(orm.Project.id)).all()
    if len(rows) == 1:
        return int(rows[0][0])
    if not rows:
        typer.secho("No project exists yet.", fg="red")
    else:
        typer.secho("Several projects exist; choose one with --project:", fg="red")
        for project_id, name in rows:
            typer.echo(f"  {project_id}  {name}")
    raise typer.Exit(1)


def generate_setup_code() -> str:
    """Twelve characters in three groups, about 59 bits: far beyond guessing
    at the throttled rate of a few attempts per quarter hour."""
    chars = "".join(secrets.choice(SETUP_CODE_ALPHABET) for _ in range(12))
    return "-".join(chars[i : i + 4] for i in range(0, 12, 4))


@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", help="Address to listen on."),
    # Hosts such as Render choose the port and pass it in $PORT.
    port: int = typer.Option(8000, envvar="PORT", help="Port to listen on."),
    workers: int = typer.Option(2, envvar="WEB_CONCURRENCY", help="Worker processes."),
    migrate: bool = typer.Option(True, help="Apply database migrations before starting."),
    forwarded_allow_ips: str = typer.Option(
        "127.0.0.1",
        envvar="SHABETZ_FORWARDED_ALLOW_IPS",
        help=(
            "Proxies trusted to report the real client address. Set this to your "
            "reverse proxy's address, or per-address sign-in throttling will see "
            "every visitor as the proxy."
        ),
    ),
) -> None:
    """Run the hosted server that people sign in to over the internet."""
    import uvicorn

    from .config import get_settings
    from .db.migrate import upgrade_to_head

    settings = get_settings()
    if migrate:
        upgrade_to_head(settings.database_url)

    with session_scope() as db:
        # With Google sign-in everyone signs up for themselves.
        needs_first_admin = not settings.firebase_enabled and not setup_is_complete(db)

    if needs_first_admin and not settings.setup_token:
        # Workers are separate processes that read settings from the
        # environment, so the code is passed on through it.
        code = generate_setup_code()
        os.environ["SHABETZ_SETUP_TOKEN"] = code
        get_settings.cache_clear()
        banner = "=" * 60
        typer.secho(
            f"\n{banner}\n  No administrator exists yet.\n"
            f"  Open this site and enter setup code:  {code}\n"
            f"  The code changes each time the server restarts until\n"
            f"  the first administrator has been created.\n{banner}\n",
            fg="yellow",
            bold=True,
        )

    if settings.environment == "prod" and not settings.cookie_secure:
        typer.secho(
            "Warning: SHABETZ_COOKIE_SECURE is off. Behind HTTPS it should be on, "
            "or session cookies can be sent over plain http.",
            fg="red",
        )

    uvicorn.run(
        "shabetz.api.main:app",
        host=host,
        port=port,
        workers=workers,
        proxy_headers=True,
        forwarded_allow_ips=forwarded_allow_ips,
    )


@app.command("desktop")
def desktop(
    port: int = typer.Option(8765),
    no_window: bool = typer.Option(False, help="Serve without opening a window."),
) -> None:
    """Run the desktop app, as the packaged Windows executable does."""
    from .desktop import main

    raise typer.Exit(main(["--port", str(port), *(["--no-window"] if no_window else [])]))


@app.command("create-admin")
def create_admin(
    email: str = typer.Option(..., prompt=True),
    full_name: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True),
    organization: str = typer.Option("", help="Name of the project the account administers."),
) -> None:
    """Create the first administrator account, and its project."""
    with session_scope() as db:
        if setup_is_complete(db):
            typer.secho("An account already exists; use the web interface.", fg="red")
            raise typer.Exit(1)
        user = bootstrap_first_admin(
            db, email=email, full_name=full_name, password=password, project_name=organization
        )
        typer.secho(f"Created administrator {user.email}", fg="green")


@app.command("seed-demo")
def seed_demo(
    divisions: int = typer.Option(4, help="How many divisions to create."),
    per_division: int = typer.Option(15, help="People in each division."),
    shifts: int = typer.Option(3, help="Equal shift windows per day."),
    owner: str = typer.Option("", help="Email of an account to make the project's admin."),
) -> None:
    """Create an example project.

    This is demonstration data, not built-in domain: every name here is a value
    an administrator would otherwise type into the setup wizard.
    """
    rng = random.Random(SEED)

    with session_scope() as db:
        owner_user = None
        if owner:
            owner_user = db.scalar(select(orm.User).where(orm.User.email == owner.strip().lower()))
            if owner_user is None:
                typer.secho(f"No account for {owner}.", fg="red")
                raise typer.Exit(1)
        project = orm.Project(name="Demo organisation")
        if owner_user is not None:
            project.members = [orm.ProjectMember(user_id=owner_user.id, role=ProjectRole.ADMIN)]
        db.add(project)
        db.flush()
        pid = project.id

        ladder = [
            orm.ProficiencyLevel(project_id=pid, name=name, rank=rank)
            for rank, name in enumerate(["Beginner", "Intermediate", "Expert", "Master"])
        ]
        db.add_all(ladder)

        skill_names = ["Cleaning", "Coding", "Team Leader", "Division Manager"]
        skills = [orm.Skill(project_id=pid, name=name) for name in skill_names]
        db.add_all(skills)

        division_rows = [
            orm.Division(project_id=pid, name=f"Division {chr(ord('A') + i)}", display_order=i)
            for i in range(divisions)
        ]
        db.add_all(division_rows)

        duration = 24 / shifts
        templates = [
            orm.ShiftTemplate(
                project_id=pid,
                name=f"Window {i + 1}",
                start_hour=i * duration,
                duration_hours=duration,
            )
            for i in range(shifts)
        ]
        db.add_all(templates)
        db.flush()

        by_skill = {s.name: s for s in skills}
        rank_of = {level.name: level for level in ladder}

        day_window = orm.ShiftTemplate(
            project_id=pid, name="Day desk", start_hour=8.0, duration_hours=8.0
        )
        db.add(day_window)
        db.flush()

        JobSpec = tuple[
            orm.Job,
            list[orm.ShiftTemplate],
            list[tuple[orm.Skill, orm.ProficiencyLevel, int | None]],
        ]
        jobs: list[JobSpec] = [
            (
                orm.Job(
                    project_id=pid,
                    name="Facility care",
                    required_people_per_shift=4,
                    division_policy=DivisionPolicy.ACTIVE_DIVISION_PREFERRED,
                ),
                templates,
                [
                    (by_skill["Cleaning"], rank_of["Intermediate"], None),
                    (by_skill["Team Leader"], rank_of["Expert"], 1),
                ],
            ),
            (
                orm.Job(
                    project_id=pid,
                    name="Feature development",
                    required_people_per_shift=2,
                    division_policy=DivisionPolicy.ANY_DIVISION,
                ),
                templates,
                [
                    (by_skill["Coding"], rank_of["Expert"], None),
                    (by_skill["Team Leader"], rank_of["Expert"], 1),
                ],
            ),
            (
                orm.Job(
                    project_id=pid,
                    name="Data entry",
                    required_people_per_shift=1,
                    division_policy=DivisionPolicy.ACTIVE_DIVISION_PREFERRED,
                ),
                [day_window],
                [(by_skill["Division Manager"], rank_of["Master"], 1)],
            ),
        ]
        for job, windows, requirements in jobs:
            db.add(job)
            db.flush()
            for window in windows:
                db.add(orm.JobShiftTemplate(job_id=job.id, shift_template_id=window.id))
            for skill, level, count in requirements:
                db.add(
                    orm.JobSkillRequirement(
                        job_id=job.id,
                        skill_id=skill.id,
                        min_level_id=level.id,
                        required_count=count,
                        is_leadership=count is not None,
                    )
                )

        # Skill minimums per division come from the feasibility analysis: two
        # windows need disjoint leads, so a division short of leaders is
        # understaffed every duty day regardless of its total head count.
        for division in division_rows:
            for index in range(per_division):
                person = orm.Person(
                    project_id=pid,
                    full_name=f"{division.name} member {index + 1}",
                    division_id=division.id,
                    external_ref=f"{division.display_order}-{index + 1:03d}",
                )
                db.add(person)
                db.flush()
                for weekday in range(7):
                    db.add(orm.PersonWorkingDay(person_id=person.id, weekday=weekday))

                grants: list[tuple[orm.Skill, orm.ProficiencyLevel]] = [
                    (by_skill["Cleaning"], rank_of["Intermediate"]),
                ]
                if index < 5:
                    grants.append((by_skill["Team Leader"], rank_of["Expert"]))
                if index < 2:
                    grants.append((by_skill["Division Manager"], rank_of["Master"]))
                if index < 8:
                    grants.append((by_skill["Coding"], rank_of["Expert"]))
                for skill, level in grants:
                    db.add(
                        orm.PersonSkill(person_id=person.id, skill_id=skill.id, level_id=level.id)
                    )
                rng.random()

        save_settings(
            db,
            pid,
            SchedulingSettings(
                rest_period_hours=8.0,
                rotation_enabled=True,
                rotation_block_days=2,
                organization_name="Demo organisation",
                setup_completed=True,
            ),
        )

    typer.secho(
        f"Created project {pid} with {divisions} divisions x {per_division} people, "
        f"{shifts} windows and {len(jobs)} jobs.",
        fg="green",
    )


PROJECT_OPTION = typer.Option(None, help="Project id; may be left out when only one exists.")


@app.command("feasibility")
def feasibility(project: int | None = PROJECT_OPTION) -> None:
    """Report whether a project's configuration can be staffed."""
    with session_scope() as db:
        report = JobOrchestrationService(db, _choose_project(db, project)).feasibility()

    typer.secho(f"Verdict: {report.verdict.value}", bold=True)
    typer.echo(f"  person-shifts per day : {report.person_shifts_per_day}")
    typer.echo(f"  peak concurrent       : {report.peak_concurrent_people}")
    typer.echo(f"  minimum distinct/day  : {report.minimum_distinct_needed}")
    for division in report.divisions:
        typer.echo(
            f"  {division.division_name}: {division.headcount} people, "
            f"~{division.expected_available:.1f} available -> {division.verdict.value}"
        )
        for message in division.messages:
            typer.secho(f"      {message}", fg="yellow")
    for message in report.messages:
        typer.secho(f"  {message}", fg="yellow")


@app.command("schedule")
def schedule(
    start: str = typer.Option(..., help="First day, YYYY-MM-DD."),
    end: str = typer.Option("", help="Last day, YYYY-MM-DD. Defaults to start + 13 days."),
    persist: bool = typer.Option(False, help="Store the run so it can be exported."),
    project: int | None = PROJECT_OPTION,
) -> None:
    """Generate a schedule and print a summary."""
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end) if end else start_date + timedelta(days=13)

    with session_scope() as db:
        service = JobOrchestrationService(db, _choose_project(db, project))
        schedule_id, result, params = service.generate(start_date, end_date)
        if persist:
            service.persist(schedule_id, result, params, created_by=None)

        summary = result.summary
        typer.secho(f"Schedule {start_date} to {end_date}", bold=True)
        typer.echo(f"  assignments        : {summary.total_assignments}")
        typer.echo(
            f"  staff used         : {summary.people_used} / {summary.total_people} "
            f"({summary.utilization_rate * 100:.0f}%)"
        )
        typer.echo(f"  understaffed shifts: {summary.understaffed_shift_count}")
        typer.echo(f"  borrowed staff     : {summary.division_fallback_count}")

        rotation = list(summary.active_division_by_day.items())[:6]
        if rotation:
            typer.echo(
                "  active division    : " + ", ".join(f"{day}={div}" for day, div in rotation)
            )
        if persist:
            typer.secho(f"  run id             : {schedule_id}", fg="green")


if __name__ == "__main__":
    app()

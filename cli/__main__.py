"""
templeton CLI — start, report, and monitor Templeton test runs.

Usage:
    templeton up [--tier 1|2] [--inspect-tls]
    templeton report --run <run_id> --results <path>
    templeton monitor --run <run_id>
"""

import os
import sys
import uuid

import click

# Allow `python -m cli` to import from shared/ when running from repo root
_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


@click.group()
def cli():
    """Templeton — adversarial navigation test environment."""


@cli.command()
@click.option(
    "--tier",
    default="1",
    type=click.Choice(["1", "2"]),
    show_default=True,
    help="Test tier: 1=Playtest (fixed), 2=War Game (procedural)",
)
@click.option(
    "--inspect-tls",
    is_flag=True,
    default=False,
    help="Enable TLS interception for Groq model traffic inspection",
)
@click.option(
    "--config",
    "config_file",
    default=None,
    type=click.Path(exists=True),
    help="Path to a custom trap configuration YAML",
)
def up(tier, inspect_tls, config_file):
    """Start the full Templeton stack and issue a run ID."""
    from state_token import generate_secret

    run_id = str(uuid.uuid4())
    secret = os.environ.get("TEMPLETON_SECRET") or generate_secret()

    # Persist run context so `templeton report` and `templeton monitor` can find it
    run_file = os.path.join(_repo_root, ".templeton-run")
    with open(run_file, "w") as f:
        f.write(f"run_id={run_id}\n")
        f.write(f"tier={tier}\n")

    env = {
        **os.environ,
        "TEMPLETON_SECRET": secret,
        "TEMPLETON_RUN_ID": run_id,
        "TEMPLETON_TIER": tier,
    }

    click.echo(f"Run ID:    {run_id}")
    click.echo(f"Start URL: http://templetoncounty.gov/?run={run_id}")
    click.echo(f"Proxy:     http://localhost:8080")
    click.echo("")

    compose_cmd = ["docker", "compose", "up", "--build"]
    os.execvpe("docker", compose_cmd, env)


@cli.command()
@click.option(
    "--run",
    "run_id",
    default=None,
    help="Run ID (defaults to most recent run from .templeton-run)",
)
@click.option(
    "--results",
    required=True,
    type=click.Path(exists=True),
    help="Path to agent result JSON file or directory of result files",
)
def report(run_id, results):
    """Generate the harness report for a completed run. (Phase 7)"""
    if run_id is None:
        run_id = _read_run_id()
    click.echo(f"[templeton report] run={run_id} results={results}")
    click.echo("Not yet implemented — Phase 7.")


@cli.command()
@click.option(
    "--run",
    "run_id",
    default=None,
    help="Run ID to monitor (defaults to most recent run)",
)
def monitor(run_id):
    """Stream a live harness report during a run. (Phase 6)"""
    if run_id is None:
        run_id = _read_run_id()
    click.echo(f"[templeton monitor] run={run_id}")
    click.echo("Not yet implemented — Phase 6.")


def _read_run_id() -> str:
    run_file = os.path.join(_repo_root, ".templeton-run")
    if not os.path.exists(run_file):
        raise click.ClickException(
            "No .templeton-run file found. Pass --run <run_id> explicitly "
            "or run `templeton up` first."
        )
    with open(run_file) as f:
        for line in f:
            if line.startswith("run_id="):
                return line.strip().split("=", 1)[1]
    raise click.ClickException("Could not read run_id from .templeton-run.")


if __name__ == "__main__":
    cli()

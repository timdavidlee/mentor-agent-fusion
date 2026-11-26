"""Command line: `dealer-gen generate` and `dealer-gen check`."""

from pathlib import Path
from typing import Annotated

import typer

from generator.checks import run_checks
from generator.config import DEFAULT_MASTER_SEED, DEFAULT_OUT_DIR, GeneratorConfig

app = typer.Typer(help="Generate the multi-tenant dealer dataset and check it.")


@app.command()
def generate(
    out: Annotated[Path, typer.Option(help="Output directory.")] = DEFAULT_OUT_DIR,
    seed: Annotated[int, typer.Option(help="Master seed.")] = DEFAULT_MASTER_SEED,
    check: Annotated[bool, typer.Option(help="Run the acceptance checks afterwards.")] = True,
) -> None:
    """Write visible and hidden output for every tenant."""
    path = GeneratorConfig(master_seed=seed, out_dir=out).make_in_dir()
    typer.echo(f"wrote {path}")
    if check:
        _check(path, deterministic=True)


@app.command()
def check(
    out: Annotated[Path, typer.Option(help="Output directory to check.")] = DEFAULT_OUT_DIR,
    deterministic: Annotated[bool, typer.Option(help="Also regenerate and compare bytes.")] = True,
) -> None:
    """Run the section 9 acceptance checks against existing output."""
    _check(out, deterministic=deterministic)


def _check(path: Path, *, deterministic: bool) -> None:
    report = run_checks(path, deterministic=deterministic)
    typer.echo(report.text())
    if not report.ok:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

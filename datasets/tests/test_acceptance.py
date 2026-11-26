"""Spec section 9: every acceptance check passes for every tenant."""

from pathlib import Path

import pytest

from generator.checks import Report
from generator.config import GeneratorConfig

CHECKS = [
    "2 schema identity",
    "3 integrity: keys",
    "3 integrity: events",
    "4 own rule exact",
    "5 wrong rules wrong",
    "6 answers agree",
    "7 habits kept rules",
    "8 separation",
]


@pytest.mark.parametrize("check", CHECKS)
def test_check_passes(report: Report, check: str) -> None:
    results = [r for r in report.results if r.check == check]
    assert results, f"check {check!r} did not run"
    failures = [f"{r.tenant}: {r.detail}" for r in results if not r.ok]
    assert not failures, "\n".join(failures)


def test_every_tenant_and_concept_checked(report: Report) -> None:
    own = [r for r in report.results if r.check == "4 own rule exact"]
    assert len(own) == 2 * 4  # tenants A and C, four concepts each


def test_deterministic(tmp_path: Path, out_dir: Path) -> None:
    again = GeneratorConfig().make_in_dir(tmp_path / "again")
    files = sorted(p.relative_to(out_dir) for p in out_dir.rglob("*") if p.is_file())
    assert files == sorted(p.relative_to(again) for p in again.rglob("*") if p.is_file())
    for rel in files:
        assert (out_dir / rel).read_bytes() == (again / rel).read_bytes(), rel


def test_make_returns_one_frame_per_table() -> None:
    frames = GeneratorConfig().make()
    assert len(frames) == 17
    assert set(frames["tenant"]["tenant_id"]) == {11, 13}

from pathlib import Path

import pytest

from generator.checks import Report, run_checks
from generator.config import GeneratorConfig


@pytest.fixture(scope="session")
def out_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return GeneratorConfig().make_in_dir(tmp_path_factory.mktemp("generated"))


@pytest.fixture(scope="session")
def report(out_dir: Path) -> Report:
    # determinism is tested on its own in test_acceptance.py
    return run_checks(out_dir, deterministic=False)

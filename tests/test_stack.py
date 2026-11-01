"""Smoke test: every library imports from its pinned submodule, alongside quantstack."""

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("package, repo", [("sppricer", "sp-pricer"), ("volsurface", "volsurface"),
                                           ("btlab", "backtest-lab"), ("lobkit", "microstructure-lab"),
                                           ("risklab", "risk-lab")])
def test_library_installed_from_submodule(package, repo):
    module = importlib.import_module(package)
    assert (ROOT / "projects" / repo) in Path(module.__file__).resolve().parents

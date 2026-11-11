"""Smoke test: in a clone, every library imports from its pinned submodule, alongside quantstack.

Outside a clone (tests run from the PyPI sdist), there are no submodules: the libraries come from PyPI,
so the check is skipped rather than failed.
"""

import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("package, repo", [("sppricer", "sp-pricer"), ("volsurface", "volsurface"),
                                           ("btlab", "backtest-lab"), ("lobkit", "microstructure-lab"),
                                           ("risklab", "risk-lab")])
def test_library_installed_from_submodule(package, repo):
    if not (ROOT / "projects" / repo / "pyproject.toml").exists():
        pytest.skip(f"projects/{repo} is not checked out (not a quant-stack clone)")
    module = importlib.import_module(package)
    assert (ROOT / "projects" / repo) in Path(module.__file__).resolve().parents

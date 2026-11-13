"""S8's hand-entered notes: every row builds a valid note that matches its saved surfaces."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

STUDIES = Path(__file__).resolve().parents[1] / "studies"
if not (STUDIES / "s8_estimated_value.py").exists():          # the PyPI sdist ships tests, not studies
    pytest.skip("studies/ not present (not a quant-stack clone)", allow_module_level=True)
spec = importlib.util.spec_from_file_location("s8", STUDIES / "s8_estimated_value.py")
s8 = importlib.util.module_from_spec(spec)
sys.modules["s8"] = s8                      # dataclasses look their module up here
spec.loader.exec_module(s8)


def test_every_note_row_is_consistent():
    notes = pd.read_csv(s8.NOTES)
    assert notes["note_id"].is_unique and len(notes) >= 2
    for _, row in notes.iterrows():
        note = s8.product(row)
        assert np.all(np.diff(note.simulation_times) > 0) and 2.9 < note.simulation_times[-1] < 3.1
        assert set(s8.years(row.pricing_date, row.autocall_dates)) <= set(note.simulation_times)
        assert row.estimated_value < row.issue_price and row.source_url.startswith("https://www.sec.gov/")
        for name, level in zip(row.underlyings.split(";"), note.initial_levels, strict=True):
            _, spot = s8.load_surface(name, row.pricing_date)       # the surface is that day's close
            assert abs(spot - level) < 1e-6 * level

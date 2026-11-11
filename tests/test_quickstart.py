"""The README's Quick start block runs as written and still shows what its comments claim."""

import re
from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"


def test_readme_quick_start_runs():
    text = README.read_text(encoding="utf-8")
    section = text.split("## Quick start", 1)[1]
    code = re.search(r"```python\n(.*?)```", section, re.S).group(1)
    ns: dict = {}
    exec(compile(code, "README.md (Quick start)", "exec"), ns)
    flat, skew, risk = ns["flat"], ns["skew"], ns["risk"]
    # the smile lowers the note, by far more than Monte Carlo error
    assert flat.price - skew.price > 10 * (flat.std_error + skew.std_error)
    assert risk["es"] >= risk["var"] > 0
    # the numbers in the comments are the seeded results, to within one unit of the printed digit: the
    # surface fit moves by ~1e-5 across supported scipy versions, enough to flip a rounding near a boundary
    assert abs(flat.price - 104.74) <= 0.01 and abs(skew.price - 102.03) <= 0.01
    assert abs(risk["var"] - 77) <= 1 and abs(risk["es"] - 135) <= 1

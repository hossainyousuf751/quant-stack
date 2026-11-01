"""S5: skew in option VaR. risk-lab Study 3's books, priced off a fitted smile instead of one flat vol.

Books (spot 100, 3-month options, as in risk-lab examples/03_option_var.py): covered call (share
+ short 105 call), protective put (share + long 95 put), short ATM straddle. Each is valued three ways
in the same lognormal spot scenarios (vol = the surface's 3-month ATM vol):

    flat ATM     one vol for every option and every scenario (risk-lab Study 3's assumption)
    sticky K     each option keeps its strike's implied vol from the smile when spot moves
    sticky K/S   the smile moves with spot; each option takes the vol of its new moneyness

Only full revaluation is used, so differences come from the vol rule, not from a Taylor expansion.
Surfaces: volsurface's synthetic chain, and the saved SPX snapshot rescaled to spot 100 if present.
Run: python studies/s5_skew_option_var.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from risklab import OptionPosition, Portfolio, full_revaluation_var, gbm_scenarios
from volsurface import fit_surface, synthetic_chain

SNAPSHOT = Path(__file__).resolve().parent.parent / "projects" / "volsurface" / "data"
BOOKS = {
    "covered call": dict(shares=1, options=[OptionPosition(105, 0.25, True, -1)]),
    "protective put": dict(shares=1, options=[OptionPosition(95, 0.25, False, 1)]),
    "short straddle": dict(options=[OptionPosition(100, 0.25, True, -1), OptionPosition(100, 0.25, False, -1)]),
}


def run(label: str, vol_fn) -> pd.DataFrame:
    atm = float(vol_fn(100.0, 0.25))
    rows = []
    for h in (1, 10):
        scen = gbm_scenarios(np.array([[atm**2 / 252]]), 200_000, horizon_days=h, seed=0)
        for book, kw in BOOKS.items():
            row = {"horizon_days": h, "book": book}
            for rule, extra in (("flat ATM", {}), ("sticky K", {"vol_fn": vol_fn, "sticky": "strike"}),
                                ("sticky K/S", {"vol_fn": vol_fn, "sticky": "moneyness"})):
                res = full_revaluation_var([Portfolio(100.0, atm, **kw, **extra)], scen, alpha=0.01)
                row[f"VaR99 {rule}"], row[f"ES99 {rule}"] = res["var"], res["es"]
            rows.append(row)
    table = pd.DataFrame(rows).set_index(["horizon_days", "book"])
    print(f"\n=== {label}: 3-month ATM vol {atm:.2%}, 95 put vol {float(vol_fn(95.0, 0.25)):.2%}, "
          f"105 call vol {float(vol_fn(105.0, 0.25)):.2%}; 200,000 scenarios, seed 0")
    with pd.option_context("display.float_format", "{:.3f}".format, "display.width", 200):
        print(table[[c for c in table.columns if c.startswith("VaR")]].to_string())
        print(table[[c for c in table.columns if c.startswith("ES")]].to_string())
    return table


if __name__ == "__main__":
    quotes, truth = synthetic_chain(seed=0)
    synthetic = fit_surface(quotes, truth["spot"]).ssvi_surface
    run("Synthetic SSVI surface, spot 100", lambda K, T: synthetic.implied_vol(K, T))

    files = sorted(SNAPSHOT.glob("SPX_20*.csv"))
    if files:
        q = pd.read_csv(files[-1])
        spot = float(q["spot"].iloc[0])
        spx = fit_surface(q, spot, max_rel_spread=0.3).svi_af_surface
        run(f"SPX {files[-1].stem[-8:]}, arbitrage-free SVI, rescaled to spot 100",
            lambda K, T: spx.implied_vol(np.asarray(K, dtype=float) * spot / 100.0, T))
    else:
        print(f"\nNo SPX snapshot in {SNAPSHOT}; skipping the real-data part.")

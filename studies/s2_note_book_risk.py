"""S2: risk of a structured-note book. Where do linear VaR approximations break?

A dealer is short four notes on two underlyings (A at 100, B at 50) and may delta-hedge with shares:

    N1 Phoenix on A          3y quarterly, 2% memory coupon, autocall 100% from year 1, protection 60%
    N2 worst-of Phoenix A/B  same terms
    N3 reverse convertible A 1y, 2% quarterly coupon, European knock-in at 70%
    N4 worst-of RC A/B       1.5y, 2% quarterly coupon, European knock-in at 60%

10-day 99% VaR and 97.5% ES by three methods: delta-normal (sppricer bump Greeks, normal P&L),
delta-gamma-vega (the same Greeks on simulated scenarios) and full revaluation (each note repriced
from a validated price grid). Implied vol moves against spot in every scenario (dvol = -0.8 x return
of A), so vega matters. Stress tests reprice directly, under flat vol and under local vol with
volsurface's shifted surfaces. Run: python studies/s2_note_book_risk.py   (about 3 minutes)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from risklab import (
    Portfolio,
    Scenario,
    full_revaluation_var,
    gbm_scenarios,
    historical_scenarios,
    simulate_dcc_t,
    stress_test,
)
from scipy.stats import norm
from sppricer import BarrierReverseConvertible, Market, PhoenixAutocallable, Underlying, bump_greeks
from volsurface import SSVIParams, fit_surface, synthetic_chain
from volsurface.synthetic import DEFAULT_EXPIRIES

from quantstack.adapters.notes import GridNotePosition, StructuredNotePosition
from quantstack.adapters.surface import local_vol_setup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _plot import LS, C, finish  # noqa: E402

H_DAYS, N_SCEN, N_PATHS, SEED = 10, 20_000, 20_000, 7
HORIZON = H_DAYS / 252
SPOT_VOL_BETA = -0.8   # implied vol change per unit return of A
CORR = np.array([[1.0, 0.6], [0.6, 1.0]])
MARKET = Market((Underlying("A", 100.0, 0.20, 0.02), Underlying("B", 50.0, 0.28, 0.015)), 0.03, CORR)
QUARTERS = tuple(0.25 * k for k in range(1, 13))
NOTES = {
    "N1 Phoenix A": (PhoenixAutocallable((100.0,), QUARTERS, 0.02, first_autocall_index=3), [0]),
    "N2 worst-of Phoenix": (PhoenixAutocallable((100.0, 50.0), QUARTERS, 0.02, first_autocall_index=3), [0, 1]),
    "N3 reverse convertible A": (BarrierReverseConvertible((100.0,), (0.25, 0.5, 0.75, 1.0), 0.02, 0.70), [0]),
    "N4 worst-of RC": (BarrierReverseConvertible((100.0, 50.0), (0.25, 0.5, 0.75, 1.0, 1.25, 1.5), 0.02, 0.60),
                       [0, 1]),
}
QUANTITY = -10.0       # the dealer sold 10 of each (per 100 notional)


def sub_market(assets: list[int]) -> Market:
    return Market(tuple(MARKET.underlyings[i] for i in assets), MARKET.rate, CORR[np.ix_(assets, assets)])


def with_spot_vol_rule(spot_mult: np.ndarray) -> Scenario:
    return Scenario(spot_mult=spot_mult, vol_shift=SPOT_VOL_BETA * (spot_mult[:, 0] - 1), elapsed=HORIZON)


class OnAssets:
    """Route a two-asset Scenario to a note that references a subset of the assets."""

    def __init__(self, position, assets: list[int]):
        self.position, self.assets = position, assets

    def value(self, s: Scenario):
        m = np.column_stack([s.spot(i) for i in self.assets])
        return self.position.value(Scenario(spot_mult=m, vol_shift=s.vol_shift, skew_shift=s.skew_shift,
                                            elapsed=s.elapsed))


def main() -> None:
    # Greeks, positions and grids
    greeks, grids, direct = {}, {}, {}
    for name, (note, assets) in NOTES.items():
        m = sub_market(assets)
        g = bump_greeks(note, m, n_paths=50_000, seed=SEED)
        greeks[name] = pd.DataFrame({"delta": g.delta, "gamma": g.gamma, "vega": g.vega},
                                    index=[MARKET.underlyings[i].name for i in assets])
        pos = StructuredNotePosition(note, m, QUANTITY, n_paths=N_PATHS, seed=SEED)
        direct[name] = OnAssets(pos, assets)
        grid = GridNotePosition(pos, HORIZON)
        check = grid.validate(n_points=20)
        print(f"{name}: price {g.price:.2f}; grid vs direct max error {check['max_abs_error']:.3f} "
              f"({check['max_error_in_se']:.1f} SE), mean {check['mean_abs_error']:.3f}")
        grids[name] = OnAssets(grid, assets)
    print("\nPer-note Greeks (per 100 notional; vega per vol point):")
    print(pd.concat(greeks).round(4).to_string())

    # book Greeks per asset (currency units), and the delta hedge in shares
    delta, gamma, vega = np.zeros(2), np.zeros(2), 0.0
    for name, (_, assets) in NOTES.items():
        for row, i in zip(greeks[name].itertuples(), assets, strict=True):
            delta[i] += QUANTITY * row.delta
            gamma[i] += QUANTITY * row.gamma
            vega += QUANTITY * row.vega
    hedge = [Portfolio(u.spot, u.vol, shares=-delta[i], underlying=i) for i, u in enumerate(MARKET.underlyings)]
    print(f"\nBook delta (shares) {np.round(delta, 3)}, gamma {np.round(gamma, 4)}, vega/vol pt {vega:.3f}; "
          f"hedge: {np.round(-delta, 3)} shares")

    spots = MARKET.spots
    cov = np.outer(MARKET.vols, MARKET.vols) * CORR / 252
    sets = {"lognormal (model covariance)": gbm_scenarios(cov, N_SCEN, H_DAYS, seed=1).spot_mult}
    hist, _ = simulate_dcc_t(4000, seed=1)
    sets["fat-tailed (simulated DCC-t history)"] = historical_scenarios(hist.iloc[:, :2], H_DAYS).spot_mult

    rows = []
    for set_name, mult in sets.items():
        clipped = np.mean((mult < 0.61) | (mult > 1.39))
        mult = np.clip(mult, 0.61, 1.39)                  # the price grid spans 0.6-1.4
        print(f"{set_name}: {len(mult):,} scenarios, {clipped:.2%} of spot moves clipped to the grid")
        scen = with_spot_vol_rule(mult)
        dS = spots * (mult - 1)
        dvol_pts = 100 * np.asarray(scen.vol_shift)
        for hedged in (False, True):
            h = -delta * hedged
            d_book = delta + h
            sd = np.sqrt(d_book @ (np.outer(spots, spots) * cov * H_DAYS) @ d_book)
            dn_var, dn_es = -norm.ppf(0.01) * sd, sd * norm.pdf(norm.ppf(0.025)) / 0.025
            dgv = dS @ d_book + 0.5 * (dS**2) @ gamma + vega * dvol_pts
            full = full_revaluation_var(list(grids.values()) + (hedge if hedged else []), scen, 0.01)
            full975 = full_revaluation_var(list(grids.values()) + (hedge if hedged else []), scen, 0.025)
            rows.append({"scenarios": set_name, "book": "delta-hedged" if hedged else "unhedged",
                         "VaR99 delta-normal": dn_var, "VaR99 delta-gamma-vega": -np.quantile(dgv, 0.01),
                         "VaR99 full reval": full["var"], "ES97.5 delta-normal": dn_es,
                         "ES97.5 delta-gamma-vega": -dgv[dgv <= np.quantile(dgv, 0.025)].mean(),
                         "ES97.5 full reval": full975["es"]})
    table = pd.DataFrame(rows).set_index(["scenarios", "book"])
    print(f"\n{H_DAYS}-day VaR (99%) and ES (97.5%) of the book, currency units "
          f"(book short {-QUANTITY:.0f} x 100 notional of each note):")
    with pd.option_context("display.float_format", "{:.2f}".format, "display.width", 220):
        print(table.to_string())

    print("\nStress tests, flat vol (direct revaluation, no time decay), P&L per position:")
    stresses = stress_test({**direct, **{f"hedge {u.name}": p for u, p in zip(MARKET.underlyings, hedge, strict=True)}})
    print(stresses.round(2).to_string())

    # local-vol stresses: reshape the smile with volsurface's shifted surfaces
    expiries = (*DEFAULT_EXPIRIES, 3.0)
    qa, ta = synthetic_chain(spot=100.0, expiries=expiries, seed=0)
    qb, tb = synthetic_chain(spot=50.0, expiries=expiries, params=SSVIParams(-0.6, 1.2, 0.4), seed=1)
    surfaces = [fit_surface(qa, ta["spot"]).ssvi_surface, fit_surface(qb, tb["spot"]).ssvi_surface]
    lv_market, _ = local_vol_setup(surfaces, CORR)
    named = {"vol +5": Scenario(vol_shift=0.05), "skew steeper (-0.03 per unit k)": Scenario(skew_shift=-0.03),
             "spot -20%": Scenario(spot_mult=0.8), "spot -20%, vol +5, steeper": Scenario(0.8, 0.05, -0.03)}
    lv_positions = {}
    for name, (note, assets) in NOTES.items():
        m = Market(tuple(lv_market.underlyings[i] for i in assets), 0.0, CORR[np.ix_(assets, assets)],
                   curves=tuple(lv_market.curves[i] for i in assets), discount_curve=lv_market.discount_curve)
        pos = StructuredNotePosition(note, m, QUANTITY, n_paths=10_000, seed=SEED,
                                     surfaces=[surfaces[i] for i in assets], dt=1 / 52)
        lv_positions[name] = OnAssets(pos, assets)
    print("\nStress tests, local vol from synthetic SSVI surfaces (shifted surfaces), P&L per position:")
    print(stress_test(lv_positions, named).round(2).to_string())

    # P&L profile against A's spot (B unchanged), with the spot-vol rule
    import matplotlib.pyplot as plt

    m_a = np.linspace(0.65, 1.35, 57)
    mult = np.column_stack([m_a, np.ones_like(m_a)])
    scen = with_spot_vol_rule(mult)
    dS = spots * (mult - 1)
    full = full_revaluation_var(list(grids.values()), scen, 0.5)["pnl"]
    lin = dS @ delta
    dg = lin + 0.5 * dS**2 @ gamma
    dgv = dg + vega * 100 * np.asarray(scen.vol_shift)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for i, (lab, y) in enumerate((("full revaluation", full), ("delta", lin), ("delta-gamma", dg),
                                  ("delta-gamma-vega", dgv))):
        ax.plot(100 * m_a, y, color=C[i], ls=LS[i], label=lab)
    for b, txt in ((60, "60% barrier"), (70, "70% knock-in")):
        ax.axvline(b, color="#888888", lw=0.8, ls=":")
        ax.text(b + 0.5, ax.get_ylim()[0], txt, fontsize=8, color="#555555", va="bottom")
    ax.set_xlabel("spot of A after 10 days (% of today), B unchanged")
    ax.set_ylabel("P&L of the unhedged book")
    print(finish(fig, ax, "s2_pnl_profile.png", "S2: short-note book P&L vs spot, Taylor vs full revaluation"))
    i75 = np.argmin(np.abs(m_a - 0.75))
    print(f"At A = 75%: full {full[i75]:.1f}, delta {lin[i75]:.1f}, delta-gamma {dg[i75]:.1f}, "
          f"delta-gamma-vega {dgv[i75]:.1f}")


if __name__ == "__main__":
    main()

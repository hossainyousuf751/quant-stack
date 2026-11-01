"""S1: skew and the autocallable. How much does pricing off the smile, not one flat vol, move a Phoenix?

Every product here is short a down-and-in put on the worst performer, so its value hinges on the
put skew. Three models price each note:

    flat ATM vol        each underlying's ATM implied vol at maturity, the usual flat-vol shortcut
    flat barrier vol    the implied vol at the protection-barrier strike, the "skew-aware" shortcut
    local vol           Dupire local vol from the fitted surface (sppricer.LocalVolModel)

All legs run in the same LocalVolModel on the same option-implied forward curves and random numbers
(a constant local vol is exact GBM), so differences between models are paired and precise.

Part 1 uses volsurface's synthetic chain (a known SSVI surface); part 2 the saved CBOE SPX/NDX
snapshot from projects/volsurface/data, if present, and cross-checks volsurface's own M5 table.
Run: python studies/s1_skew_autocallable.py   (about 5 minutes with the snapshot)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sppricer import LocalVolModel, PhoenixAutocallable
from volsurface import SSVIParams, fit_surface, synthetic_chain
from volsurface.synthetic import DEFAULT_EXPIRIES

from quantstack.adapters.surface import local_vol_setup

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _plot import LS, C, finish  # noqa: E402

N_PATHS, SEED, MATURITY = 100_000, 42, 3.0
SNAPSHOT_DIR = Path(__file__).resolve().parent.parent / "projects" / "volsurface" / "data"


class ConstantVol:
    """A LocalVolSource with one vol everywhere: GBM on the surface's forward curve."""

    def __init__(self, curve, vol: float):
        self.curve, self.vol = curve, vol

    def local_vol(self, K, T):
        return np.full(np.shape(K), self.vol)


def phoenix(spots, protection=0.60, coupon_barrier=0.70) -> PhoenixAutocallable:
    """sppricer's README note: 3y quarterly, 2% quarterly memory coupon, autocall at 100% from year 1."""
    return PhoenixAutocallable(tuple(spots), tuple(0.25 * k for k in range(1, 13)), coupon_rate=0.02,
                               coupon_barrier=coupon_barrier, autocall_barrier=1.0,
                               protection_barrier=protection, memory=True, first_autocall_index=3)


def paired(pv: np.ndarray) -> np.ndarray:
    return 0.5 * (pv[: len(pv) // 2] + pv[len(pv) // 2:])


def mean_se(x: np.ndarray) -> tuple[float, float]:
    return float(x.mean()), float(x.std(ddof=1) / np.sqrt(len(x)))


def autocall_profile(note: PhoenixAutocallable, paths: np.ndarray) -> pd.Series:
    """P(called on each date), then P(reaching maturity) and P(knocked in at maturity)."""
    worst = (paths / np.asarray(note.initial_levels)).min(axis=2)
    alive = np.ones(len(worst), dtype=bool)
    out = {}
    for i, t in enumerate(note.observation_times[:-1]):
        called = alive & (i >= note.first_autocall_index) & (worst[:, i] >= note.autocall_barrier)
        out[f"call {t:g}y"] = called.mean()
        alive &= ~called
    out["to maturity"] = alive.mean()
    out["knocked in"] = (alive & (worst[:, -1] < note.protection_barrier)).mean()
    return pd.Series(out)


def run(label: str, surfaces: list, correlation, flat_surfaces=None) -> dict:
    """Price the note (and a barrier sweep) under the three models; flat vols come from flat_surfaces."""
    flat_surfaces = flat_surfaces or surfaces
    market, lv_model = local_vol_setup(surfaces, correlation)
    spots = market.spots
    note = phoenix(spots)
    times = np.asarray(note.simulation_times)
    atm = [float(s.implied_vol(s.curve.forward(MATURITY), MATURITY)) for s in flat_surfaces]

    def flat_model(vols):
        return LocalVolModel([ConstantVol(s.curve, v) for s, v in zip(surfaces, vols, strict=True)],
                             dt=lv_model.dt)

    def barrier_vols(protection):
        return [float(s.implied_vol(protection * x, MATURITY)) for s, x in zip(flat_surfaces, spots, strict=True)]

    models = {"flat ATM vol": flat_model(atm), "flat barrier vol": flat_model(barrier_vols(0.60)),
              "local vol": lv_model}
    paths = {m: model.simulate(market, times, N_PATHS, seed=SEED) for m, model in models.items()}
    pv = {m: paired(note.discounted_payoff(p, market)) for m, p in paths.items()}

    rows = []
    for m in models:
        price, se = mean_se(pv[m])
        diff, dse = mean_se(pv[m] - pv["flat ATM vol"])
        rows.append({"model": m, "fair value": price, "SE": se, "issuer margin vs 100": 100 - price,
                     "vs flat ATM": diff, "SE of diff": dse})
    table = pd.DataFrame(rows).set_index("model")
    profile = pd.DataFrame({m: autocall_profile(note, p) for m, p in paths.items()})

    sweep = {}
    for protection in np.round(np.arange(0.50, 0.81, 0.05), 2):
        n = phoenix(spots, protection, max(0.70, protection))
        flat_b = flat_model(barrier_vols(protection)).simulate(market, times, N_PATHS, seed=SEED)
        sweep[protection] = {"flat ATM vol": paired(n.discounted_payoff(paths["flat ATM vol"], market)).mean(),
                             "flat barrier vol": paired(n.discounted_payoff(flat_b, market)).mean(),
                             "local vol": paired(n.discounted_payoff(paths["local vol"], market)).mean()}

    print(f"\n=== {label}: spots {np.round(spots, 2).tolist()}, flat ATM vol at {MATURITY:g}y "
          f"{[f'{v:.2%}' for v in atm]}, {N_PATHS:,} paths, seed {SEED}")
    with pd.option_context("display.float_format", "{:.3f}".format, "display.width", 200):
        print(table.to_string())
        print("\nAutocall / knock-in probabilities:")
        print(profile.T.to_string())
    lv_share = [s.n_clamped / s.n_local_vol for s in surfaces]
    print(f"local-vol strike-grid points on a guard rail (flat extrapolation, NaN or clip): "
          f"{[f'{x:.1%}' for x in lv_share]}")
    return {"table": table, "profile": profile, "sweep": pd.DataFrame(sweep).T, "market": market,
            "paths": paths, "note": note, "lv_model": lv_model}


def dt_check(surfaces, correlation) -> pd.DataFrame:
    """Euler bias: the local-vol price at dt = 1/126, 1/252, 1/504 (independent streams)."""
    rows = []
    for steps in (126, 252, 504):
        market, model = local_vol_setup(surfaces, correlation, dt=1 / steps)
        note = phoenix(market.spots)
        pv = paired(note.discounted_payoff(model.simulate(market, np.asarray(note.simulation_times),
                                                          N_PATHS, seed=SEED + steps), market))
        price, se = mean_se(pv)
        rows.append({"steps per year": steps, "fair value": price, "SE": se})
    return pd.DataFrame(rows)


def path_share_beyond_fit(surface, n_paths=20_000) -> float:
    """Share of simulated (path, day) points whose log-moneyness lies outside the fitted quotes."""
    market, model = local_vol_setup([surface])
    grid, full = model.simulate_grid(market, np.array([MATURITY]), n_paths, seed=1)
    k = np.log(full[:, 1:, 0] / surface.curve.forward(grid[1:]))
    lo, hi = surface.k_range
    return float(((k < lo) | (k > hi)).mean())


def plot_sweep(results: dict, name: str, title: str) -> Path:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.5))
    i = 0
    for label, res in results.items():
        for m in res["sweep"].columns:
            ax.plot(100 * res["sweep"].index, res["sweep"][m], color=C[i % len(C)], ls=LS[i % len(LS)],
                    marker="o", ms=3, label=f"{label}: {m}")
            i += 1
    ax.axhline(100, color="#888888", lw=0.8)
    ax.set_xlabel("protection barrier (% of initial)")
    ax.set_ylabel("fair value per 100")
    return finish(fig, ax, name, title)


if __name__ == "__main__":
    # Part 1: synthetic chains (known SSVI surfaces), quotes out to 3y so the note needs no extrapolation in T
    expiries = (*DEFAULT_EXPIRIES, 3.0)
    q1, t1 = synthetic_chain(spot=100.0, expiries=expiries, seed=0)
    q2, t2 = synthetic_chain(spot=50.0, expiries=expiries, params=SSVIParams(-0.6, 1.2, 0.4), seed=1,
                             atm_vol=lambda T: 0.22 + 0.04 * np.exp(-2.0 * np.asarray(T, dtype=float)))
    a = fit_surface(q1, t1["spot"]).ssvi_surface
    b = fit_surface(q2, t2["spot"]).ssvi_surface
    corr = np.array([[1.0, 0.6], [0.6, 1.0]])
    synthetic = {"single asset": run("Synthetic, single asset", [a], None),
                 "worst-of": run("Synthetic, two-asset worst-of, correlation 0.6", [a, b], corr)}

    print("\nEuler check, synthetic worst-of under local vol:")
    print(dt_check([a, b], corr).round(3).to_string(index=False))
    print(f"\nShare of simulated (path, day) points beyond the fitted moneyness range, asset A: "
          f"{path_share_beyond_fit(a):.2%}")
    print(plot_sweep(synthetic, "s1_price_vs_barrier_synthetic.png",
                     "S1: Phoenix fair value vs protection barrier, synthetic chains"))

    # Part 2: the saved CBOE SPX / NDX close, as in volsurface's M5/M6 study
    paths = {t: sorted(SNAPSHOT_DIR.glob(f"{t}_20*.csv")) for t in ("SPX", "NDX")}
    if not all(paths.values()):
        print(f"\nNo SPX/NDX snapshot in {SNAPSHOT_DIR}; skipping the real-data part.")
        sys.exit(0)
    fits = {}
    for ticker, spread in (("SPX", 0.3), ("NDX", 0.5)):
        quotes = pd.read_csv(paths[ticker][-1])
        fits[ticker] = fit_surface(quotes, float(quotes["spot"].iloc[0]), max_rel_spread=spread)
    af = []
    for f in fits.values():
        s = f.local_vol_surface()           # arbitrage-free SVI on pillar expiries (volsurface M6)
        s.k_range = f.svi_af_surface.k_range  # local_vol_surface() builds a new surface without it
        af.append(s)
    corr = np.array([[1.0, 0.9], [0.9, 1.0]])
    real = {"SPX/NDX worst-of": run(f"CBOE close {paths['SPX'][-1].stem[-8:]}, SPX/NDX worst-of, correlation 0.9",
                                    af, corr),
            "SPX single asset": run("CBOE close, SPX single asset", af[:1], None)}
    essvi = [f.essvi_surface for f in fits.values()]
    m, lv = local_vol_setup(essvi, corr)
    note = real["SPX/NDX worst-of"]["note"]
    pv_essvi = paired(note.discounted_payoff(lv.simulate(m, np.asarray(note.simulation_times), N_PATHS, seed=SEED),
                                             m))
    print(f"\neSSVI local vol (under-states the SPX put wing), same note: {pv_essvi.mean():.2f} "
          f"+/- {pv_essvi.std(ddof=1) / np.sqrt(len(pv_essvi)):.2f}")
    print("volsurface M5/M6 table for comparison (200k paths, flat-rate discounting): "
          "flat 100.41, eSSVI 96.14, arb-free SVI 96.42")
    print(plot_sweep(real, "s1_price_vs_barrier_spx.png", "S1: Phoenix fair value vs protection barrier, SPX/NDX"))

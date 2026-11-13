"""S8: what does the issuer's own estimated value imply? Real US autocallables, priced off that day's surfaces.

Since 2013 US issuers of structured notes state an "estimated value" in each final pricing supplement
(form 424B2 on SEC EDGAR): what the note is worth on the issuer's own models, discounted at its internal
funding rate. It sits below the $1,000 issue price; the difference is fees, hedging costs and profit.

This study prices real notes with quant-stack: the issuer's terms, the same day's SPX/NDX/RUT surfaces
(volsurface, arbitrage-free SSVI, fitted to the CBOE close), Dupire local vol in sp-pricer, and asks:
1. Fair value at the option-implied risk-free curve, against the issuer's estimate.
2. The implied funding spread: the extra discount rate that brings our fair value down to the issuer's
   estimate. Issuers discount at their own funding rate, so this should be positive and similar across
   one issuer's notes on one day.
3. A model check that needs no funding assumption: two notes from the same issuer and day, identical but
   for the coupon, must differ in estimated value by what the coupon difference is worth.

Terms are entered by hand from each pricing supplement into s8_notes/notes.csv, one row per note with its
EDGAR link (no document parsing). The fitted surfaces for each pricing date are in s8_notes/surfaces/
(our own model output; the raw CBOE quotes they were fitted to are not redistributed).

Not modelled, and stated: payment dates a few business days after each valuation date (discounted at the
valuation date); calendar postponements; the issuer's own, unpublished, volatility and correlation.
Correlation is the realised one-year daily-return correlation before pricing (public Yahoo data).

Run: python studies/s8_estimated_value.py   (about 3 minutes; downloads index history once)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from sppricer import PhoenixAutocallable, price_mc
from volsurface import SSVISurface

from quantstack.adapters.surface import local_vol_setup

HERE = Path(__file__).resolve().parent
NOTES = HERE / "s8_notes" / "notes.csv"
SURFACES = HERE / "s8_notes" / "surfaces"
DATA = HERE.parent / "data"
YAHOO = {"SPX": "^GSPC", "NDX": "^NDX", "RUT": "^RUT"}
TREASURY = ["^IRX", "^FVX"]                                  # 13-week and 5-year yields, percent
N_PATHS, SEED, DT = 100_000, 8, 1 / 252


@dataclass(frozen=True)
class FlatDiscount:
    """The same forwards, discounted at a flat continuously compounded rate (here the Treasury yield)."""

    curve: object
    rate: float

    def forward(self, T):
        return self.curve.forward(T)

    def discount(self, T):
        return np.exp(-self.rate * np.asarray(T, dtype=float))


@dataclass(frozen=True)
class ShiftedDiscount:
    """A curve with the same forwards and discount factors lowered by a flat spread s: D(T) exp(-s T)."""

    curve: object
    spread: float

    def forward(self, T):
        return self.curve.forward(T)

    def discount(self, T):
        return self.curve.discount(T) * np.exp(-self.spread * np.asarray(T, dtype=float))


def years(start: str, dates: str) -> tuple[float, ...]:
    t0 = pd.Timestamp(start)
    return tuple((pd.Timestamp(d) - t0).days / 365.0 for d in dates.split(";"))     # ACT/365F


def product(row: pd.Series) -> PhoenixAutocallable:
    times = years(row.pricing_date, row.valuation_dates)
    calls = [times.index(t) for t in years(row.pricing_date, row.autocall_dates)]
    every_from_first = calls == list(range(calls[0], len(times) - 1))
    kw = {"first_autocall_index": calls[0]} if every_from_first else {"autocall_indices": tuple(calls)}
    return PhoenixAutocallable(
        initial_levels=tuple(float(x) for x in row.initial_levels.split(";")), observation_times=times,
        coupon_rate=row.coupon_per_period, coupon_barrier=row.coupon_barrier,
        autocall_barrier=row.autocall_barrier, protection_barrier=row.final_barrier,
        memory=str(row.memory) == "True", notional=row.issue_price, **kw)


def load_surface(name: str, date: str):
    meta = json.loads((SURFACES / f"{name}_{pd.Timestamp(date):%Y%m%d}.json").read_text(encoding="utf-8"))
    return SSVISurface.from_dict(meta["ssvi"]), meta["spot"]


def market_history() -> pd.DataFrame | None:
    path = DATA / "s8_market_history.csv"
    needed = set(YAHOO.values()) | set(TREASURY)

    def complete(px):
        return px is not None and needed <= set(px.columns) and px[list(needed)].notna().sum().min() > 250

    px = pd.read_csv(path, index_col=0, parse_dates=True) if path.exists() else None
    for _ in range(3):                    # Yahoo can silently return an empty column; retry, never cache a gap
        if complete(px):
            return px.ffill()
        try:
            from btlab.data import load_yfinance

            px = load_yfinance(sorted(needed), start="2024-01-01", end="2026-12-31")
        except Exception as exc:  # no yfinance or no network
            print(f"Market history unavailable ({type(exc).__name__}: {exc}).")
            return None
        if complete(px):
            DATA.mkdir(exist_ok=True)
            px.to_csv(path)
    print("Market history incomplete after 3 downloads (Yahoo returned empty tickers).")
    return None


def realised_correlation(px: pd.DataFrame, names: list[str], date: str) -> np.ndarray:
    window = px.loc[pd.Timestamp(date) - pd.DateOffset(years=1):pd.Timestamp(date), [YAHOO[n] for n in names]]
    return np.log(window).diff().dropna().corr().to_numpy()


def treasury_rate(px: pd.DataFrame, date: str, T: float) -> float:
    """Continuously compounded Treasury yield to T, linear in maturity between the 13-week and 5-year."""
    irx, fvx = px.loc[:pd.Timestamp(date), TREASURY].iloc[-1]
    return float(np.log1p((irx + (fvx - irx) * (T - 0.25) / (5 - 0.25)) / 100))


def value(note, market, model, paths=None):
    """(fair value, SE, paths) on local vol; reuse paths to revalue under a different discount curve."""
    if paths is None:
        paths = model.simulate(market, note.simulation_times, N_PATHS, seed=SEED)
    pv = note.discounted_payoff(paths, market)
    pairs = 0.5 * (pv[: N_PATHS // 2] + pv[N_PATHS // 2:])
    return float(pairs.mean()), float(pairs.std(ddof=1) / np.sqrt(len(pairs))), paths


def run() -> pd.DataFrame:
    notes = pd.read_csv(NOTES)
    px = market_history()
    if px is None:
        raise SystemExit("S8 needs index and Treasury history; run once with network access.")
    rows = []
    for _, row in notes.iterrows():
        names = row.underlyings.split(";")
        surfaces, spots = zip(*(load_surface(n, row.pricing_date) for n in names), strict=True)
        initial = [float(x) for x in row.initial_levels.split(";")]
        assert np.allclose(spots, initial, rtol=1e-6), f"{row.note_id}: surface spots {spots} != initial {initial}"
        corr = realised_correlation(px, names, row.pricing_date)
        note = product(row)
        T = note.simulation_times[-1]
        atm = [float(s.implied_vol(s.curve.forward(T), T)) for s in surfaces]
        market, local_vol = local_vol_setup(list(surfaces), correlation=corr, dt=DT, names=names, flat_vols=atm)
        disc = surfaces[names.index("SPX")].curve if "SPX" in names else surfaces[0].curve
        market = replace(market, discount_curve=disc)        # SPX parity-implied rates: the most liquid
        fair, se, paths = value(note, market, local_vol)
        flat = price_mc(note, market, N_PATHS, seed=SEED)

        def gap(s, market=market, paths=paths, note=note, ev=row.estimated_value):
            shifted = replace(market, discount_curve=ShiftedDiscount(market.discount_curve, s))
            return value(note, shifted, None, paths)[0] - ev

        spread = brentq(gap, -0.05, 0.20)
        r_tsy = treasury_rate(px, row.pricing_date, T)
        tsy = replace(market, discount_curve=FlatDiscount(disc, r_tsy))
        fair_tsy = value(note, tsy, None, paths)[0]

        def gap_tsy(s, tsy=tsy, paths=paths, note=note, ev=row.estimated_value):
            return value(note, replace(tsy, discount_curve=ShiftedDiscount(tsy.discount_curve, s)), None, paths)[0] - ev

        spread_tsy = brentq(gap_tsy, -0.05, 0.20)
        sens = {}
        for d in (-0.05, 0.05):
            c = np.clip(corr + d, -0.99, 0.99)                # shift and clip the off-diagonal only
            np.fill_diagonal(c, 1.0)
            m, lv = local_vol_setup(list(surfaces), correlation=c, dt=DT, names=names, flat_vols=atm)
            sens[d] = value(note, replace(m, discount_curve=disc), lv)[0]
        rows.append({
            "note": row.note_id, "coupon_pa": row.coupon_per_period * len(note.observation_times) / T,
            "corr": corr[0, 1] if len(names) == 2 else float(corr[np.triu_indices(len(names), 1)].mean()),
            "fee": row.underwriting_fee, "issuer_ev": row.estimated_value, "fair_lv": fair, "se": se,
            "fair_flat_atm": flat.price, "fair_minus_ev": fair - row.estimated_value,
            "implied_spread_bp": 1e4 * spread, "fair_tsy": fair_tsy, "spread_over_tsy_bp": 1e4 * spread_tsy,
            "tsy_3y": r_tsy, "corr_minus_5pts": sens[-0.05], "corr_plus_5pts": sens[0.05],
            "rf_3y": -np.log(float(market.discount(T))) / T,
        })
    return pd.DataFrame(rows).set_index("note")


def report(res: pd.DataFrame) -> None:
    print(f"S8: issuer estimated value vs quant-stack fair value "
          f"({N_PATHS:,} paths, seed {SEED}, local vol dt 1/252)\n")
    cols = ["coupon_pa", "fee", "issuer_ev", "fair_lv", "se", "fair_flat_atm", "implied_spread_bp", "fair_tsy",
            "spread_over_tsy_bp"]
    print(res[cols].to_string(float_format="{:,.2f}".format, formatters={"coupon_pa": "{:.2%}".format}))
    print("\nInputs: realised 1y correlation " + ", ".join(f"{k} {v:.3f}" for k, v in res["corr"].items())
          + "; rate to maturity: option-implied " + ", ".join(f"{v:.2%}" for v in res["rf_3y"])
          + ", Treasury " + ", ".join(f"{v:.2%}" for v in res["tsy_3y"]))
    print("fair_lv and implied_spread_bp discount at the SPX option-implied curve; fair_tsy and spread_over_tsy_bp at "
          "Treasuries. A negative spread means the issuer values the note above our model at that curve.")
    print("Correlation -/+ 0.05, fair value: " + "; ".join(
        f"{k} {r.corr_minus_5pts:,.2f} / {r.corr_plus_5pts:,.2f}" for k, r in res.iterrows()))
    if len(res) >= 2:
        a, b = res.iloc[0], res.iloc[1]
        print(f"\nSame issuer, day and structure, different coupon ({a.name} vs {b.name}):")
        print(f"  issuer's estimated values differ by {b.issuer_ev - a.issuer_ev:+.2f}")
        print(f"  our fair values differ by           {b.fair_lv - a.fair_lv:+.2f} "
              "(same paths for both notes, so the difference is free of most Monte Carlo noise)")


if __name__ == "__main__":
    report(run())

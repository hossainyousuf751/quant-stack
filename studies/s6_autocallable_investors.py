"""S6: how did autocallable investors actually do? (sp-pricer notes on backtest-lab's price history)

A hypothetical 3-year Phoenix on SPY is issued on the first trading day of every month since 2005:
quarterly observations, a memory coupon paid above 70%, autocall at 100% from year 1, capital at risk
below 60% at maturity (European). The coupon is set the way an issuer sets it: at issue, using only that
day's VIX and rates, so that the model fair value is 98 per 100 (a 2-point margin). The realised SPY path
then gives the cash flows the investor actually received: the realised IRR, and the realised present
value at the issue-date rate.

If the model were unbiased, the realised present value would average to the fair value. The gap is the
model meeting history: the equity risk premium (the investor is short a down-and-in put, and puts lost
money on average) and the volatility risk premium (VIX has tended to exceed the volatility that followed).
A second set of notes with a fixed 2% quarterly coupon shows the same comparison when fair value varies.

Data, all public: SPY, VIX, and 13-week and 5-year Treasury yields from Yahoo Finance via btlab's loader,
cached under data/ (git-ignored); skipped cleanly without network.

Limitations, stated plainly:
- VIX is a 30-day, model-free variance measure on the S&P 500, used here as a flat 3-year ATM vol. It
  ignores the term structure and the skew, which matters for a note that is short a down-and-in put (S1).
- btlab's loader returns dividend-adjusted prices, so the note is written on SPY total return and priced
  with zero dividend yield. A real note on the price index has a lower forward and pays a higher coupon.
- The 3-year rate is a linear interpolation between the 13-week and 5-year yields, with no credit spread.
  Issuers fund at their own spread, so real coupons were higher than a risk-free model implies.
- Monthly notes with lives up to 3 years overlap: the 21 years of issues hold only about 7 independent
  3-year windows. Averages carry Newey-West standard errors over 36 monthly lags.

Run: python studies/s6_autocallable_investors.py   (about 30 seconds; downloads about 1 MB on first run)
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from sppricer import Market, PhoenixAutocallable, price_mc

from quantstack.adapters.notes import realised_cashflows

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _plot import LS, C, finish  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
TICKERS = ["SPY", "^VIX", "^IRX", "^FVX"]
END = "2026-10-31"
OBS = tuple(0.25 * np.arange(1, 13))         # quarterly for 3 years
TERMS = dict(coupon_barrier=0.70, autocall_barrier=1.00, protection_barrier=0.60, memory=True,
             first_autocall_index=3)
ISSUE_PRICE, MARGIN, FIXED_COUPON = 100.0, 2.0, 0.02
N_PATHS, SEED = 20_000, 7


def market_data() -> pd.DataFrame | None:
    path = DATA / "s6_spy_vix_rates.csv"
    if path.exists():
        return pd.read_csv(path, index_col=0, parse_dates=True)
    try:
        from btlab.data import load_yfinance

        px = load_yfinance(TICKERS, start="2005-01-01", end=END)
    except Exception as exc:  # no yfinance, no network, or Yahoo changed
        print(f"Market data unavailable ({type(exc).__name__}: {exc}); S6 needs SPY, VIX and rates. Skipping.")
        return None
    DATA.mkdir(exist_ok=True)
    px.to_csv(path)
    return px


def rate_3y(irx: float, fvx: float) -> float:
    """Continuously compounded 3-year rate from the 13-week and 5-year yields (in percent)."""
    y = (irx + (fvx - irx) * (3 - 0.25) / (5 - 0.25)) / 100
    return float(np.log1p(y))


def irr(cashflows: np.ndarray, times: np.ndarray, price: float = ISSUE_PRICE) -> float:
    """Annually compounded yield that prices the cash flows at the issue price."""
    return brentq(lambda y: cashflows @ (1 + y) ** -times - price, -0.99, 1.0)


def newey_west_se(x: np.ndarray, lags: int = 36) -> float:
    """Standard error of the mean of a serially correlated series (Newey and West 1987, Bartlett weights)."""
    x = np.asarray(x, dtype=float) - np.mean(x)
    n = len(x)
    var = x @ x / n
    for k in range(1, min(lags, n - 1) + 1):
        var += 2 * (1 - k / (lags + 1)) * (x[k:] @ x[:-k]) / n
    return float(np.sqrt(var / n))


def run_notes(px: pd.DataFrame) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    px = px.ffill()
    spy = px["SPY"]
    times = np.asarray(OBS)
    rows, alive = [], []
    for d0 in px.groupby(px.index.to_period("M")).head(1).index:
        idx = px.index.searchsorted([d0 + pd.DateOffset(months=3 * (i + 1)) for i in range(len(OBS))])
        known = int(np.sum(idx < len(px)))                      # observation dates already in the data
        perf = np.full(len(OBS), np.nan)
        perf[:known] = spy.iloc[idx[:known]].to_numpy() / spy.loc[d0]
        i = np.arange(len(OBS))
        callable_ = (i >= TERMS["first_autocall_index"]) & (i < len(OBS) - 1)   # maturity redeems, not calls
        called = np.flatnonzero(callable_[:known] & (perf[:known] >= TERMS["autocall_barrier"]))
        if known < len(OBS) and not len(called):
            alive.append(d0)                                    # outcome not known yet
            continue

        vol, r = px.loc[d0, "^VIX"] / 100, rate_3y(px.loc[d0, "^IRX"], px.loc[d0, "^FVX"])
        market = Market.single(spot=1.0, vol=vol, rate=r)
        base = PhoenixAutocallable(initial_levels=(1.0,), observation_times=OBS, coupon_rate=0.0, **TERMS)
        # with common random numbers the price is exactly linear in the coupon: solve, then check
        p0 = price_mc(base, market, N_PATHS, seed=SEED).price
        p1 = price_mc(replace(base, coupon_rate=FIXED_COUPON), market, N_PATHS, seed=SEED)
        coupon = FIXED_COUPON * (ISSUE_PRICE - MARGIN - p0) / (p1.price - p0)
        par = price_mc(replace(base, coupon_rate=coupon), market, N_PATHS, seed=SEED)
        assert abs(par.price - (ISSUE_PRICE - MARGIN)) < 1e-9, par.price

        row = {"issue": d0, "vix": vol, "rate": r, "coupon_pa": (1 + coupon) ** 4 - 1, "fair_se": par.std_error,
               "fixed_fair": p1.price}
        levels = np.nan_to_num(perf)[:, None]                   # dates after an autocall pay nothing anyway
        for name, c in (("", coupon), ("fixed_", FIXED_COUPON)):
            cf = realised_cashflows(replace(base, coupon_rate=c), levels)
            row[f"{name}pv"] = float(cf @ np.exp(-r * times))
            row[f"{name}irr"] = irr(cf, times)
        end = int(called[0]) if len(called) else len(OBS) - 1
        assert np.flatnonzero(cf)[-1] == end                    # the payoff code agrees on when the note ended
        life = spy.loc[d0:px.index[idx[end]]]
        row.update(years=times[end], final_perf=perf[end],
                   outcome="called" if end < len(OBS) - 1 else "par" if perf[end] >= TERMS["protection_barrier"]
                   else "loss",
                   realised_vol=float(np.log(life).diff().std() * np.sqrt(252)))
        rows.append(row)
    return pd.DataFrame(rows).set_index("issue"), alive


def report(notes: pd.DataFrame, alive: list[pd.Timestamp]) -> None:
    n, fair = len(notes), ISSUE_PRICE - MARGIN
    gap = notes["pv"] - fair
    fixed_gap = notes["fixed_pv"] - notes["fixed_fair"]
    rf = np.expm1(notes["rate"])
    print(f"{n} notes issued {notes.index[0]:%Y-%m} to {notes.index[-1]:%Y-%m} with a known outcome; "
          f"{len(alive)} later issues ({alive[0]:%Y-%m} to {alive[-1]:%Y-%m}) are still alive and left out.")
    print(f"Terms: {TERMS}, quarterly for 3 years; coupon set at issue for a fair value of {fair:g} "
          f"(GBM, VIX vol, {N_PATHS:,} paths, seed {SEED}; max SE {notes['fair_se'].max():.2f}).\n")

    print("Model vs history, averages over issues (+/- Newey-West SE, 36 lags):")
    print(f"  coupon set at issue (p.a.)    mean {notes['coupon_pa'].mean():.2%}, "
          f"range {notes['coupon_pa'].min():.2%} to {notes['coupon_pa'].max():.2%}; negative for "
          f"{(notes['coupon_pa'] < 0).sum()} issues "
          f"({', '.join(sorted({f'{d:%Y-%m}' for d in notes.index[notes['coupon_pa'] < 0]}))}), where a "
          "zero-coupon note is already worth more than 98: low VIX, near-zero rates, no funding spread")
    print(f"  fair value at issue           {fair:7.2f}")
    print(f"  realised PV at issue rate     {notes['pv'].mean():7.2f}")
    print(f"  realised minus fair           {gap.mean():+7.2f} +/- {newey_west_se(gap):.2f}")
    print(f"  realised IRR                  mean {notes['irr'].mean():.2%}, median {notes['irr'].median():.2%}, "
          f"worst {notes['irr'].min():.2%}; 3-year rate at issue mean {rf.mean():.2%}")
    excess = notes["irr"] - rf
    print(f"  IRR minus 3-year rate         {excess.mean():+.2%} +/- {newey_west_se(excess):.2%}")
    print(f"  VIX at issue                  {notes['vix'].mean():.1%}; realised vol over each note's life "
          f"{notes['realised_vol'].mean():.1%} (VIX higher in {(notes['vix'] > notes['realised_vol']).mean():.0%} "
          "of notes)")
    print(f"\nSame notes with a fixed {FIXED_COUPON:.0%} quarterly coupon ({(1 + FIXED_COUPON) ** 4 - 1:.2%} p.a.):")
    print(f"  fair value at issue           mean {notes['fixed_fair'].mean():.2f}, "
          f"range {notes['fixed_fair'].min():.2f} to {notes['fixed_fair'].max():.2f}")
    print(f"  realised PV at issue rate     mean {notes['fixed_pv'].mean():.2f}")
    print(f"  realised minus fair           {fixed_gap.mean():+.2f} +/- {newey_west_se(fixed_gap):.2f}")
    print(f"  realised IRR                  mean {notes['fixed_irr'].mean():.2%}, "
          f"worst {notes['fixed_irr'].min():.2%}\n")

    out = notes["outcome"].value_counts().reindex(["called", "par", "loss"], fill_value=0)
    called_at = notes.loc[notes["outcome"] == "called", "years"].value_counts().sort_index()
    print("Outcomes: " + ", ".join(f"{k} {v} ({v / n:.0%})" for k, v in out.items()))
    print("Autocalled after (years): " + ", ".join(f"{t:g}: {v}" for t, v in called_at.items()))
    print(f"Lowest SPY level at a 3-year maturity: {notes.loc[notes['outcome'] != 'called', 'final_perf'].min():.0%} "
          f"of initial (protection at {TERMS['protection_barrier']:.0%})\n")

    by_year = notes.groupby(notes.index.year).agg(
        notes=("vix", "size"), vix=("vix", "mean"), coupon_pa=("coupon_pa", "mean"), pv=("pv", "mean"),
        irr=("irr", "mean"), called=("outcome", lambda s: (s == "called").mean()),
        losses=("outcome", lambda s: (s == "loss").sum()))
    print("By issue year (coupon-at-issue notes):")
    print(by_year.to_string(formatters={"vix": "{:.1%}".format, "coupon_pa": "{:.2%}".format,
                                        "pv": "{:.2f}".format, "irr": "{:.2%}".format, "called": "{:.0%}".format}))


def plot(notes: pd.DataFrame) -> str:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(notes.index, notes["pv"], color=C[1], ls=LS[0], label="realised cash flows, PV at issue rate")
    ax.axhline(ISSUE_PRICE - MARGIN, color=C[0], ls=LS[1], label="model fair value at issue (coupon set for 98)")
    ax.axhline(ISSUE_PRICE, color="grey", lw=0.8, ls=LS[3], label="issue price")
    ax.set_ylabel("per 100 notional")
    ax.set_xlabel("issue date")
    return finish(fig, ax, "s6_fair_vs_realised.png", "S6: SPY Phoenix, what investors received vs the model")


if __name__ == "__main__":
    px = market_data()
    if px is not None:
        notes, alive = run_notes(px)
        report(notes, alive)
        print(plot(notes))

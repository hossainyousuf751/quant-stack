"""S7: market-maker inventory risk (microstructure-lab's Avellaneda-Stoikov P&L through risk-lab's VaR backtests)

microstructure-lab runs the Avellaneda and Stoikov (2008) quoter inside its zero-intelligence order book,
where fills depend on queue position and arrive just before adverse moves. Its README reports the mean and
standard deviation of P&L. A risk desk asks a different question: how bad is a bad session, and do the
standard VaR models know?

Each 5-minute session (T = 300 s, the README's setting) is one period. For three risk aversions and both
quoting rules, 2,500 independent sessions give a P&L series (in ticks). On it:
- the tail of the P&L itself: probability of a loss, 99% VaR and 97.5% ES, and mean P&L per unit of ES;
- rolling forecasts by risk-lab's four models (historical 500, normal 500, EWMA, FHS 1000), backtested
  over the same last 1,500 sessions: Kupiec and Christoffersen at 99%, Acerbi-Szekely Z2 for 97.5% ES.

Sessions are independent by construction, so there is no volatility clustering for EWMA or FHS to find:
this tests the models' distributional assumptions, not their dynamics. The paper's own fill model
(lobkit.simulate_as) is run once for contrast.

Units. P&L is in ticks per session. risk-lab's VaR models scale exactly with their input, but fit_garch
is conditioned for daily returns of about 0.01, so P&L is passed in units of 10,000 ticks and the
forecasts are scaled back. Checked: historical, normal and EWMA agree across units to 1e-15. FHS agrees to
1e-10 at the median, but a few GARCH refits find slightly different optima under other units, which
moves those forecasts by up to about 2% and the mean FHS VaR by about 0.1%.

Run: python studies/s7_market_maker_risk.py   (about 7 minutes, offline)
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
from lobkit import ASParams, simulate_lob
from lobkit.market_making import fill_intensity, simulate_as, simulate_as_lob
from risklab import acerbi_szekely_z2, backtest_var, var_es_ewma, var_es_fhs, var_es_historical, var_es_normal
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _plot import LS, C, finish  # noqa: E402

GAMMAS = (0.001, 0.005, 0.02)
STRATEGIES = ("inventory", "symmetric")
N_SESSIONS, T = 2500, 300.0
VAR_ALPHA, ES_ALPHA = 0.01, 0.025
TEST_START = 1000                    # the longest window (FHS) is 1,000 sessions; all models are tested after it
UNIT = 1e4                           # ticks per unit passed to risk-lab (conditioning of fit_garch only)
MODELS = {
    "historical": lambda r, a: var_es_historical(r, a, window=500),
    "normal": lambda r, a: var_es_normal(r, a, window=500),
    "ewma": lambda r, a: var_es_ewma(r, a, warmup=500),
    "fhs": lambda r, a: var_es_fhs(r, a, window=1000),
}


def calibrate() -> ASParams:
    """The paper's inputs measured on the book, exactly as microstructure-lab's example 05 does."""
    q = simulate_lob(400_000, seed=1).quotes
    mid = pd.Series(0.5 * (q["bid_px"] + q["ask_px"]).to_numpy(), index=pd.to_datetime(q["ts"], unit="s"))
    sigma = float(mid.resample("1s").last().ffill().diff().std())
    _, A, k = fill_intensity()
    print(f"Calibrated on the book: sigma = {sigma:.3f} ticks/sqrt(s), A = {A:.3f} fills/s, k = {k:.3f} per tick")
    return ASParams(T=T, sigma=sigma, k=k, A=A)


def tail(pnl: np.ndarray) -> dict:
    q = np.quantile(pnl, VAR_ALPHA)
    q_es = np.quantile(pnl, ES_ALPHA)
    es = -pnl[pnl <= q_es].mean()
    return {"mean": pnl.mean(), "sd": pnl.std(ddof=1), "skew": stats.skew(pnl), "ex_kurt": stats.kurtosis(pnl),
            "p_loss": (pnl < 0).mean(), "var99": -q, "es975": es, "mean_per_es": pnl.mean() / es}


def backtests(pnl: np.ndarray) -> list[dict]:
    r = pd.Series(pnl / UNIT)
    test = slice(TEST_START, None)
    rows = []
    for name, model in MODELS.items():
        f99, f975 = model(r, VAR_ALPHA).iloc[test], model(r, ES_ALPHA).iloc[test]
        bt = backtest_var(r.iloc[test], f99, VAR_ALPHA)
        rows.append({"model": name, "mean_var99": f99["var"].mean() * UNIT, "exceptions": bt.exceptions,
                     "expected": bt.expected, "kupiec_p": bt.kupiec_p, "indep_p": bt.independence_p,
                     "z2_es975": acerbi_szekely_z2(r.iloc[test], f975["es"], f975["var"], ES_ALPHA)})
    return rows


def plot(tails: pd.DataFrame) -> str:
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    for i, s in enumerate(STRATEGIES):
        d = tails.xs(s, level="strategy")
        ax.plot(d["es975"], d["mean"], color=C[i], ls=LS[i], marker="o", label=f"{s} quotes")
        for g, row in d.iterrows():
            ax.annotate(f"γ={g:g}", (row["es975"], row["mean"]), textcoords="offset points", xytext=(6, 4), fontsize=8)
    ax.axvline(0, color="grey", lw=0.8)
    ax.set_xlabel("97.5% expected shortfall per session (ticks; > 0 is a loss)")
    ax.set_ylabel("mean P&L per session (ticks)")
    return finish(fig, ax, "s7_mm_return_vs_es.png", "S7: market making in the order book, return vs tail risk")


if __name__ == "__main__":
    params = calibrate()
    paper = simulate_as(n_paths=N_SESSIONS, seed=0).pnl
    print(f"Paper's fill model (lobkit.simulate_as defaults, {N_SESSIONS:,} sessions): mean {paper.mean():.1f}, "
          f"worst session {paper.min():+.1f}, share of losing sessions {(paper < 0).mean():.1%}. "
          "A loss VaR is meaningless there.\n")

    tails, tests = [], []
    for g in GAMMAS:
        for s in STRATEGIES:
            pnl = simulate_as_lob(replace(params, gamma=g), s, n_episodes=N_SESSIONS)["pnl"]
            pnl = pnl.to_numpy(dtype=float)
            tails.append({"gamma": g, "strategy": s, **tail(pnl)})
            tests += [{"gamma": g, "strategy": s, **row} for row in backtests(pnl)]
    tails = pd.DataFrame(tails).set_index(["gamma", "strategy"])
    tests = pd.DataFrame(tests).set_index(["gamma", "strategy", "model"])

    print(f"Session P&L in the order book ({N_SESSIONS:,} sessions of {T:g} s each, ticks):")
    print(tails.to_string(float_format="{:.2f}".format, formatters={"p_loss": "{:.1%}".format}))
    print(f"\nRolling VaR/ES forecasts backtested on sessions {TEST_START + 1:,}-{N_SESSIONS:,} "
          f"(99% VaR: Kupiec and Christoffersen p-values; 97.5% ES: Acerbi-Szekely Z2, about -0.70 rejects at 5%):")
    print(tests.to_string(float_format="{:.2f}".format,
                          formatters={"kupiec_p": "{:.3f}".format, "indep_p": "{:.3f}".format,
                                      "expected": "{:.0f}".format}))
    print(plot(tails))

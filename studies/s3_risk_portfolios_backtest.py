"""S3: risk-based portfolios under honest backtesting (risk-lab estimators, backtest-lab engine).

risk-lab compares portfolio methods by their exact true risk on synthetic data, but with no trading.
Here every method trades through backtest-lab: one-day execution lag, 5 bp costs, drift between
rebalances, walk-forward selection of the estimation window and a Deflated Sharpe ratio over every
configuration tried. Part 1 is synthetic (risk-lab's 50-asset block covariance, so true risk is known);
part 2 is risk-lab's 10-ETF universe from Yahoo Finance (skipped offline, cached under data/);
part 3 is volatility targeting with GARCH and EWMA forecasts in backtest-lab's time-series momentum.
Run: python studies/s3_risk_portfolios_backtest.py   (about 10 minutes)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from btlab import (
    CovarianceStrategy,
    TimeSeriesMomentum,
    annual_vol,
    check_lookahead,
    cost_sensitivity,
    deflated_sharpe,
    risk_report,
    run_backtest,
    sharpe,
    walk_forward,
)
from risklab import (
    block_covariance,
    equal_weight,
    fit_garch,
    garch_variance,
    hrp,
    inverse_variance,
    ledoit_wolf,
    min_variance,
    risk_parity,
    sample_cov,
    simulate_garch_t,
    var_es_fhs,
)

DATA = Path(__file__).resolve().parent.parent / "data"
EVERY, COST_BPS = 21, 5.0
WINDOWS = (60, 126, 252, 504)


def lw(x: np.ndarray) -> np.ndarray:
    return ledoit_wolf(x)[0]


METHODS = {
    "1/N": (sample_cov, equal_weight),
    "inverse variance": (sample_cov, inverse_variance),
    "min-var sample long-only": (sample_cov, lambda c: min_variance(c, long_only=True)),
    "min-var LW long-only": (lw, lambda c: min_variance(c, long_only=True)),
    "risk parity (LW)": (lw, risk_parity),
    "HRP (sample)": (sample_cov, hrp),
}


_WEIGHTS: dict = {}


class CachedCovarianceStrategy(CovarianceStrategy):
    """CovarianceStrategy whose weights are memoised per (configuration, price frame).

    walk_forward and the per-configuration table both need every configuration's weights; long-only
    minimum variance takes ~40 s per configuration on 50 assets, so compute each once.
    """

    def weights(self, prices: pd.DataFrame) -> pd.DataFrame:
        key = (self, id(prices), prices.shape)
        if key not in _WEIGHTS:
            _WEIGHTS[key] = super().weights(prices)
        return _WEIGHTS[key]


def configs() -> tuple[list[dict], list[str]]:
    grid, labels = [], []
    for name, (est, alloc) in METHODS.items():
        for w in WINDOWS:
            grid.append({"estimator": est, "allocator": alloc, "window": w, "min_history": max(WINDOWS),
                         "every": EVERY})
            labels.append(f"{name}, {w}d")
    return grid, labels


def fhs(r: pd.Series) -> pd.DataFrame:
    return var_es_fhs(r, 0.01, window=500, refit_every=63)


def study(prices: pd.DataFrame, label: str, true_cov: np.ndarray | None = None) -> pd.DataFrame:
    grid, labels = configs()
    wf = walk_forward(prices, CachedCovarianceStrategy, grid, train_days=756, test_days=252, rebalance=EVERY,
                      execution_lag=1, cost_bps=COST_BPS)
    rows = []
    for j, (params, lab) in enumerate(zip(grid, labels, strict=True)):
        w = CachedCovarianceStrategy(**params).weights(prices)
        res = run_backtest(prices, w, rebalance=EVERY, execution_lag=1, cost_bps=COST_BPS)
        s = res.summary()
        row = {"config": lab, "sharpe": s["sharpe"], "annual_return": s["annual_return"],
               "realised_vol": s["annual_vol"], "annual_turnover": s.get("annual_turnover", np.nan)}
        if true_cov is not None:   # ex-ante true vol of the weights actually held at each rebalance
            held = res.weights.fillna(0.0).to_numpy()
            held = held[np.abs(held).sum(axis=1) > 0]       # skip warm-up rebalances that hold nothing
            row["true_vol"] = float(np.mean(np.sqrt(np.einsum("ti,ij,tj->t", held, true_cov, held))))
        rows.append(row)
        assert np.allclose(wf.trial_returns[j], res.returns), "walk_forward and run_backtest disagree"
    table = pd.DataFrame(rows).set_index("config")
    best = wf.best_in_sample
    dsr = deflated_sharpe(wf.trial_returns[best], wf.trial_sharpes)
    print(f"\n=== {label}: {prices.shape[1]} assets, {len(prices):,} days, rebalance every {EVERY} days, "
          f"lag 1, {COST_BPS:g} bp")
    with pd.option_context("display.float_format", "{:.3f}".format, "display.width", 200):
        print(table.to_string())
    print(f"Best in-sample: {labels[best]} (Sharpe {wf.trial_sharpes[best]:.2f}); Deflated Sharpe over "
          f"{len(labels)} configurations {dsr:.3f}; walk-forward out-of-sample Sharpe {sharpe(wf.oos_returns):.2f}")

    hrp_turnover = table.loc[[f"HRP (sample), {w}d" for w in WINDOWS], "annual_turnover"]
    mv_turnover = table.loc[[f"min-var LW long-only, {w}d" for w in WINDOWS], "annual_turnover"]
    print("Annual turnover by window, HRP vs min-var LW long-only:")
    print(pd.DataFrame({"HRP": hrp_turnover.to_numpy(), "min-var LW": mv_turnover.to_numpy()},
                       index=pd.Index(WINDOWS, name="window")).round(2).to_string())

    chosen = {name: CachedCovarianceStrategy(*METHODS[name], window=252, min_history=max(WINDOWS), every=EVERY)
              for name in METHODS}
    print("FHS 99% VaR backtests (252-day window), cost sensitivity of net Sharpe (0 / 5 / 20 / 50 bp):")
    out = []
    for name, strat in chosen.items():
        w = strat.weights(prices)
        res = run_backtest(prices, w, rebalance=EVERY, execution_lag=1, cost_bps=COST_BPS)
        rep = risk_report(res, fhs, alpha=0.01)
        cs = cost_sensitivity(prices, w, bps_grid=(0, 5, 20, 50), rebalance=EVERY, execution_lag=1)
        srs = {f"SR@{b}bp": v for b, v in zip(cs.cost_bps, cs.sharpe, strict=True)}
        out.append({"method": name, "exceptions": rep["exceptions"], "expected": rep["expected"],
                    "kupiec_p": rep["kupiec_p"], **srs})
    with pd.option_context("display.float_format", "{:.3f}".format, "display.width", 200):
        print(pd.DataFrame(out).set_index("method").to_string())
    print(f"Look-ahead check of a CovarianceStrategy: passed={check_lookahead(chosen['HRP (sample)'], prices)[0]}")
    return table


def synthetic_prices(seed: int = 0) -> tuple[pd.DataFrame, np.ndarray]:
    cov = block_covariance(n_blocks=5, block_size=10, rho_within=0.6, rho_between=0.2, seed=seed)
    rng = np.random.default_rng(seed)
    r = rng.multivariate_normal(np.full(len(cov), 0.06 / 252), cov / 252, size=252 * 12)
    idx = pd.bdate_range("2012-01-02", periods=len(r))
    return pd.DataFrame(100 * np.cumprod(1 + r, axis=0), idx, [f"A{i:02d}" for i in range(len(cov))]), cov


ETFS = ["SPY", "EFA", "EEM", "TLT", "IEF", "LQD", "HYG", "GLD", "DBC", "VNQ"]


def etf_prices() -> pd.DataFrame | None:
    path = DATA / "s3_etfs.csv"
    if path.exists():
        return pd.read_csv(path, index_col=0, parse_dates=True)
    try:
        from btlab.data import load_yfinance

        px = load_yfinance(ETFS, start="2007-06-01", end="2025-12-31")
    except Exception as exc:  # no yfinance, no network, or Yahoo changed: the synthetic part stands alone
        print(f"\nETF data unavailable ({type(exc).__name__}: {exc}); skipping part 2.")
        return None
    DATA.mkdir(exist_ok=True)
    px.to_csv(path)
    return px


# Volatility targeting: causal vol forecasts for backtest-lab's TimeSeriesMomentum (annualised, row t uses <= t)
def rolling_vol(r: pd.DataFrame) -> pd.DataFrame:
    return r.rolling(63, min_periods=31).std() * np.sqrt(252)


def ewma_vol(r: pd.DataFrame, lam: float = 0.94) -> pd.DataFrame:
    """RiskMetrics: sigma_t^2 = lam sigma_{t-1}^2 + (1 - lam) r_t^2, zero mean."""
    return np.sqrt((r**2).ewm(alpha=1 - lam, adjust=False).mean() * 252)


def garch_vol(r: pd.DataFrame, refit_every: int = 252, min_obs: int = 500) -> pd.DataFrame:
    """risk-lab GARCH(1,1), parameters refitted once a year on data up to the refit date only."""
    out = pd.DataFrame(np.nan, index=r.index, columns=r.columns)
    for c in r.columns:
        x = r[c].fillna(0.0).to_numpy()
        for start in range(min_obs, len(x), refit_every):
            p = fit_garch(x[:start])
            mu = x[:start].mean()
            v = garch_variance(x[: min(start + refit_every, len(x))] - mu, p, v0=float(np.var(x[:start])))
            # v[t + 1] is the forecast made after observing x[t]: the vol known at row t
            known = np.sqrt(v[start + 1:start + refit_every + 1] * 252)
            out.iloc[start:start + len(known), out.columns.get_loc(c)] = known
    return out


def vol_targeting() -> None:
    sims = [simulate_garch_t(3500, nu=5.0, mu=0.0003, seed=s)["r"] for s in range(10)]
    r = pd.concat(sims, axis=1, keys=[f"G{i}" for i in range(10)]).iloc[:, :10]
    r.columns = [f"G{i}" for i in range(10)]
    prices = 100 * (1 + r).cumprod()
    realised = r.rolling(21).std().shift(-21) * np.sqrt(252)          # next month's realised vol, for scoring
    rows = []
    for name, est in (("rolling 63d std", None), ("EWMA 0.94", ewma_vol), ("GARCH(1,1)", garch_vol)):
        strat = TimeSeriesMomentum(target_vol=0.10, max_weight=1.0, vol_estimator=est)
        w = strat.weights(prices)
        res = run_backtest(prices, w, rebalance="W", execution_lag=1, cost_bps=COST_BPS)
        # TSMom scales each asset to target_vol, then divides by the number of assets, so the per-asset
        # sleeve (n x weight x return, weight from the previous close) is what should run at 10%
        sleeves = (w.shape[1] * w.shift(1) * r).iloc[600:]
        fc = (est or rolling_vol)(prices.pct_change(fill_method=None))
        err = (fc - realised).iloc[600:-21]
        rows.append({"vol forecast": name, "mean sleeve vol (target 0.10)": float(sleeves.std().mean() * np.sqrt(252)),
                     "sleeve vol spread": float(sleeves.std().std() * np.sqrt(252)),
                     "portfolio realised vol": annual_vol(res.returns.iloc[600:]),
                     "net Sharpe": sharpe(res.returns.iloc[600:]),
                     "forecast RMSE (vol pts)": 100 * float(np.sqrt(np.nanmean(err.to_numpy() ** 2))),
                     "forecast bias (vol pts)": 100 * float(np.nanmean(err.to_numpy()))})
    print("\n=== Volatility targeting: TSMom on 10 GARCH-t assets (vol clusters), 10% target per asset sleeve")
    with pd.option_context("display.float_format", "{:.3f}".format, "display.width", 200):
        print(pd.DataFrame(rows).set_index("vol forecast").to_string())
    print("Look-ahead check with the GARCH estimator: passed="
          f"{check_lookahead(TimeSeriesMomentum(vol_estimator=garch_vol), prices.iloc[:1500], n_cutoffs=2)[0]}")


if __name__ == "__main__":
    prices, cov = synthetic_prices()
    study(prices, "Synthetic: risk-lab block covariance (true risk known)", true_cov=cov)
    etfs = etf_prices()
    if etfs is not None:
        study(etfs.dropna(), "Live: risk-lab's 10-ETF universe, Yahoo Finance adjusted closes")
    vol_targeting()

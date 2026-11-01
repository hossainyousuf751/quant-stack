"""S4: costs from the order book. Does a strong same-second order-flow relationship survive as a trade?

1. Calibrate trading costs with lobkit.calibrate_costs on the zero-intelligence simulator and on the
   Binance BTCUSDT / ETHUSDT recordings in projects/microstructure-lab/data (if present).
2. Daily crypto momentum (Yahoo Finance, skipped offline) under backtest-lab's flat 5 bp costs versus
   the calibrated spread + square-root impact costs.
3. Intraday: order-flow imbalance (OFI) and queue-imbalance signals on 1-second mid-price bars, traded
   through backtest-lab with a look-ahead check, execution lags of 1-5 bars, calibrated costs, the
   Deflated Sharpe ratio across all signal variants, and walk-forward selection.

microstructure-lab finds that OFI explains most of the same-bucket mid change (R^2 ~ 0.6). The question
here is what is left once a trade has to be placed after the signal and pay the spread.
Run: python studies/s4_costs_from_order_book.py   (about 5 minutes)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from btlab import (
    FlatBps,
    Strategy,
    TimeSeriesMomentum,
    check_lookahead,
    deflated_sharpe,
    run_backtest,
    sharpe,
    walk_forward,
)
from lobkit import bucket_features, calibrate_costs, l1_features, ofi_price_impact, simulate_lob, to_bars
from lobkit.recorder import load_recording

from quantstack.adapters.costs import SECONDS_PER_DAY_24H, cost_model_from_book, impact_coefficient

ROOT = Path(__file__).resolve().parent.parent
RECORDINGS = ROOT / "projects" / "microstructure-lab" / "data"
DATA = ROOT / "data"
BAR = "1s"
BARS_PER_YEAR = 365 * 86_400


def calibrations() -> dict[str, dict]:
    sim = simulate_lob(n_events=400_000, seed=1)
    cals = {"simulator": calibrate_costs(sim.quotes, sim.trades)}
    for sym in ("btcusdt", "ethusdt"):
        hits = sorted(RECORDINGS.glob(f"{sym}_*"))
        if hits:
            q, t = load_recording(hits[-1])
            cals[sym.upper()] = calibrate_costs(q, t) | {"recording": hits[-1].name}
    table = pd.DataFrame(cals).T
    table["impact Y (calibrated)"] = [impact_coefficient(c) for c in cals.values()]
    print("=== Cost calibration (calibrate_costs; Y matched to the 10 s OFI impact at mean top-of-book depth)")
    with pd.option_context("display.float_format", "{:.6g}".format, "display.width", 220):
        print(table.drop(columns=["recording"], errors="ignore").T.to_string())
    if len(cals) == 1:
        print(f"No Binance recording under {RECORDINGS}; the live parts use only the simulator.")
    return cals


CRYPTO = ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD", "DOGE-USD", "LTC-USD", "BNB-USD"]


def daily_crypto(cals: dict) -> None:
    path = DATA / "s4_crypto_daily.csv"
    if path.exists():
        px = pd.read_csv(path, index_col=0, parse_dates=True)
    else:
        try:
            from btlab.data import load_yfinance

            px = load_yfinance(CRYPTO, start="2018-01-01", end="2025-12-31")
            DATA.mkdir(exist_ok=True)
            px.to_csv(path)
        except Exception as exc:
            print(f"\n=== Daily crypto momentum: data unavailable ({type(exc).__name__}: {exc}); skipped.")
            return
    live = {k: v for k, v in cals.items() if k != "simulator"} or {"simulator": cals["simulator"]}
    ref = live.get("BTCUSDT", next(iter(live.values())))
    weights = TimeSeriesMomentum(lookback=90, vol_lookback=30, target_vol=0.2, max_weight=0.5).weights(px)
    print(f"\n=== Daily crypto momentum, {px.shape[1]} coins, {px.index[0].date()} to {px.index[-1].date()}, "
          "weekly rebalance, lag 1 day")
    print("Calibrated costs use the BTCUSDT recording's spread, vol and volume for every coin; altcoin books are "
          "thinner, so this flatters them.")
    rows = []
    for capital in (1e6, 1e7, 1e8):
        flat = run_backtest(px, weights, rebalance="W", cost_model=FlatBps(5.0), periods_per_year=365)
        model = cost_model_from_book(ref, SECONDS_PER_DAY_24H, capital)
        book = run_backtest(px, weights, rebalance="W", cost_model=model, periods_per_year=365)
        rows.append({"capital": capital, "Sharpe flat 5 bp": sharpe(flat.returns, 365),
                     "Sharpe calibrated": sharpe(book.returns, 365),
                     "cost/yr flat": flat.costs.sum() / (len(px) / 365),
                     "cost/yr calibrated": book.costs.sum() / (len(px) / 365)})
    with pd.option_context("display.float_format", "{:.4f}".format):
        print(pd.DataFrame(rows).set_index("capital").to_string())


class OrderFlowSignal(Strategy):
    """Trade the sign of a 1-second order-book signal, rebuilt from raw quotes up to each bar's end.

    weights(prices) only uses quotes with timestamps up to the last bar it is given, so the truncation
    test exercises the bar alignment itself: a feature that leaked a later quote would fail it.
    """

    def __init__(self, quotes: pd.DataFrame, signal: str = "ofi", threshold: float = 0.0):
        self.quotes, self.signal, self.threshold = quotes, signal, threshold

    def weights(self, prices: pd.DataFrame) -> pd.DataFrame:
        end = (prices.index[-1] - pd.Timestamp(0)).total_seconds()
        f = l1_features(self.quotes[self.quotes["ts"] < end])
        b = bucket_features(f, None, BAR)
        b.index = b.index + pd.Timedelta(BAR)          # bucket [t, t+1s) is known at t+1s: label it there
        if self.signal == "ofi":
            x = b["ofi"] / b["depth"]
        elif self.signal == "imbalance":
            x = b["imbalance"] - 0.5
        else:
            x = np.sign(b["ofi"]) + np.sign(b["imbalance"] - 0.5)
        w = np.sign(x.where(x.abs() > self.threshold, 0.0))
        return pd.DataFrame({prices.columns[0]: w}).reindex(prices.index).fillna(0.0)


def intraday(cals: dict) -> None:
    syms = [s for s in ("BTCUSDT", "ETHUSDT") if s in cals]
    if not syms:
        print("\n=== Intraday OFI signal: no recording; skipped.")
        return
    for sym in syms:
        q, t = load_recording(RECORDINGS / cals[sym]["recording"])
        f = l1_features(q)
        bars = to_bars(f, BAR, t)
        prices = bars[["close"]].rename(columns={"close": sym})
        model = cost_model_from_book(cals[sym], bar_seconds=1, capital=1e5)
        same = ofi_price_impact(bucket_features(f, t, BAR))
        print(f"\n=== Intraday {sym}: {len(prices):,} one-second bars; same-second OFI impact R^2 {same.r2:.3f}")
        print(f"look-ahead check (OFI, features rebuilt from truncated quotes): "
              f"passed={check_lookahead(OrderFlowSignal(q, 'ofi'), prices, n_cutoffs=3)[0]}")
        grid = [{"quotes": q, "signal": s, "threshold": th}
                for s in ("ofi", "imbalance", "both") for th in ((0.0, 0.25, 1.0) if s == "ofi" else
                                                                (0.0, 0.2, 0.4) if s == "imbalance" else (0.0, 1.5))]
        rows, trial = [], {}
        for lag in (1, 2, 5):
            for params in grid:
                w = OrderFlowSignal(**params).weights(prices)
                gross = run_backtest(prices, w, rebalance=1, execution_lag=lag, cost_model=FlatBps(0.0),
                                     periods_per_year=BARS_PER_YEAR)
                net = run_backtest(prices, w, rebalance=1, execution_lag=lag, cost_model=model,
                                   periods_per_year=BARS_PER_YEAR)
                key = f"{params['signal']} > {params['threshold']}, lag {lag}"
                trial[key] = net.returns
                rows.append({"variant": key, "gross SR (ann.)": sharpe(gross.returns, BARS_PER_YEAR),
                             "net SR (ann.)": sharpe(net.returns, BARS_PER_YEAR),
                             "gross bp/bar": 1e4 * gross.returns.mean(), "cost bp/bar": 1e4 * net.costs.mean(),
                             "trades/hour": 3600 * (gross.turnover > 0).mean()})
        table = pd.DataFrame(rows).set_index("variant")
        trials = pd.DataFrame(trial)
        best = trials.apply(lambda r: sharpe(r, BARS_PER_YEAR)).idxmax()
        dsr = deflated_sharpe(trials[best], trials.apply(lambda r: sharpe(r, BARS_PER_YEAR)), periods=BARS_PER_YEAR)
        with pd.option_context("display.float_format", "{:.3f}".format, "display.width", 200):
            print(table.to_string())
        print(f"Best net variant: {best}; Deflated Sharpe over {trials.shape[1]} variants: {dsr:.3f}")
        wf = walk_forward(prices, OrderFlowSignal, grid, train_days=1800, test_days=900, rebalance=1,
                          execution_lag=1, cost_model=model, periods_per_year=BARS_PER_YEAR)
        print(f"Walk-forward (30 min train, 15 min test, lag 1 bar, calibrated costs): out-of-sample net SR "
              f"{sharpe(wf.oos_returns, BARS_PER_YEAR):.2f}, mean {1e4 * wf.oos_returns.mean():.4f} bp/bar")


if __name__ == "__main__":
    cals = calibrations()
    daily_crypto(cals)
    intraday(cals)

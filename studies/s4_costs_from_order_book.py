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
from lobkit.recorder import load_depth, load_recording

from quantstack.adapters.costs import SECONDS_PER_DAY_24H, cost_model_from_book, impact_coefficient

ROOT = Path(__file__).resolve().parent.parent
RECORDINGS = ROOT / "projects" / "microstructure-lab" / "data"
DATA = ROOT / "data"
BAR = "1s"
BARS_PER_YEAR = 365 * 86_400
FEES = (0.0, 10.0)   # taker fee, bp per trade: none, and Binance's published base spot rate


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
        book = run_backtest(px, weights, rebalance="W", periods_per_year=365,
                            cost_model=cost_model_from_book(ref, SECONDS_PER_DAY_24H, capital))
        textbook = run_backtest(px, weights, rebalance="W", periods_per_year=365,
                                cost_model=cost_model_from_book(ref, SECONDS_PER_DAY_24H, capital, impact_coef=1.0))
        with_fee = run_backtest(px, weights, rebalance="W", periods_per_year=365,
                                cost_model=cost_model_from_book(ref, SECONDS_PER_DAY_24H, capital, fee_bps=10.0))
        years = len(px) / 365
        rows.append({"capital": capital, "Sharpe flat 5 bp": sharpe(flat.returns, 365),
                     "Sharpe calibrated Y": sharpe(book.returns, 365), "Sharpe Y = 1": sharpe(textbook.returns, 365),
                     "Sharpe calibrated + 10 bp fee": sharpe(with_fee.returns, 365),
                     "cost/yr flat": flat.costs.sum() / years, "cost/yr calibrated Y": book.costs.sum() / years,
                     "cost/yr Y = 1": textbook.costs.sum() / years})
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
            raise ValueError(f"unknown signal {self.signal!r}")
        w = np.sign(x.where(x.abs() > self.threshold, 0.0))
        return pd.DataFrame({prices.columns[0]: w}).reindex(prices.index).fillna(0.0)


class TouchSpread:
    """A CostModel paying the actual half-spread at the close of the bar the trade executes in.

    The calibrated model charges the median half-spread. If the spread is wide exactly when a signal
    trades (a queue just emptied, the book has gapped), the median understates the cost.
    """

    def __init__(self, half_spread: pd.Series):
        self.half_spread = half_spread                          # relative, per bar close

    def cost(self, trade_weights, date, context):
        return np.abs(trade_weights) * self.half_spread.loc[date]


class BookWalk:
    """A CostModel that fills each trade against the recorded order book (Binance, 10 levels, ~1 s snapshots).

    A buy of |dw| x capital takes the asks level by level from the last snapshot before the bar closes; the
    cost is the fill's distance from mid, relative to mid. Size beyond the 10 recorded levels is charged at
    the 10th level's price, a lower bound (counted in `beyond`). This sees the depth that is there when the
    signal fires, which an average-depth impact law cannot.
    """

    def __init__(self, depth: pd.DataFrame, bar_index: pd.DatetimeIndex, capital: float):
        snap_t = pd.to_datetime(depth["ts"], unit="s").to_numpy()
        row = np.searchsorted(snap_t, bar_index.to_numpy(), side="left") - 1      # last snapshot before bar end
        self.row = dict(zip(bar_index, np.clip(row, 0, len(depth) - 1), strict=True))
        levels = [""] + [f"_{m}" for m in range(2, 11)]
        self.ask_px, self.ask_sz = (depth[[f"ask_{k}{lv}" for lv in levels]].to_numpy() for k in ("px", "sz"))
        self.bid_px, self.bid_sz = (depth[[f"bid_{k}{lv}" for lv in levels]].to_numpy() for k in ("px", "sz"))
        self.mid = 0.5 * (depth["ask_px"] + depth["bid_px"]).to_numpy()
        self.capital, self.beyond = capital, 0

    def cost(self, trade_weights, date, context):
        dw = float(trade_weights[0])
        if dw == 0:
            return np.zeros(1)
        i = self.row[date]
        px, sz = (self.ask_px[i], self.ask_sz[i]) if dw > 0 else (self.bid_px[i], self.bid_sz[i])
        qty = abs(dw) * self.capital / self.mid[i]
        take = np.minimum(sz, np.maximum(qty - np.concatenate([[0.0], np.cumsum(sz)[:-1]]), 0.0))
        rest = qty - take.sum()
        self.beyond += rest > 1e-12
        vwap = (take @ px + rest * px[-1]) / qty
        return np.array([abs(dw) * abs(vwap - self.mid[i]) / self.mid[i]])


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
        spread_at_close = (f.set_index(pd.to_datetime(f["ts"], unit="s"))["spread"]
                           .resample(BAR, closed="left", label="right").last().reindex(prices.index).ffill())
        touch = TouchSpread((spread_at_close / 2 / prices[sym]).bfill())
        depth = load_depth(RECORDINGS / cals[sym]["recording"])
        same = ofi_price_impact(bucket_features(f, t, BAR))
        print(f"\n=== Intraday {sym}: {len(prices):,} one-second bars; same-second OFI impact R^2 {same.r2:.3f}")
        for signal in ("ofi", "imbalance"):
            print(f"look-ahead check ({signal}, features rebuilt from truncated quotes): "
                  f"passed={check_lookahead(OrderFlowSignal(q, signal), prices, n_cutoffs=3)[0]}")
        grid = [{"quotes": q, "signal": s, "threshold": th}
                for s in ("ofi", "imbalance") for th in ((0.0, 0.25, 1.0) if s == "ofi" else (0.0, 0.2, 0.4))]
        fee_models = {fee: cost_model_from_book(cals[sym], bar_seconds=1, capital=1e5, fee_bps=fee) for fee in FEES}
        rows, trial, best_w = [], {}, {}
        for lag in (1, 2, 5):
            for params in grid:
                w = OrderFlowSignal(**params).weights(prices)
                key = f"{params['signal']} > {params['threshold']}, lag {lag}"
                best_w[key] = (w, lag)
                gross = run_backtest(prices, w, rebalance=1, execution_lag=lag, cost_model=FlatBps(0.0),
                                     periods_per_year=BARS_PER_YEAR)
                row = {"variant": key, "gross SR (ann.)": sharpe(gross.returns, BARS_PER_YEAR),
                       "gross bp/bar": 1e4 * gross.returns.mean(), "trades/hour": 3600 * (gross.turnover > 0).mean()}
                row["break-even fee (bp)"] = 1e4 * gross.gross_returns.sum() / max(gross.turnover.sum(), 1e-12)
                for cap in (1e3, 1e5):
                    walk = BookWalk(depth, prices.index, cap)
                    res = run_backtest(prices, w, rebalance=1, execution_lag=lag, cost_model=walk,
                                       periods_per_year=BARS_PER_YEAR)
                    row[f"net SR, book walk ${cap:,.0f}"] = sharpe(res.returns, BARS_PER_YEAR)
                    row[f"book walk ${cap:,.0f} bp/bar"] = 1e4 * res.costs.mean()
                for fee, m in fee_models.items():
                    net = run_backtest(prices, w, rebalance=1, execution_lag=lag, cost_model=m,
                                       periods_per_year=BARS_PER_YEAR)
                    row[f"net SR, fee {fee:g} bp"] = sharpe(net.returns, BARS_PER_YEAR)
                    if fee == 0:
                        trial[key] = net.returns
                        row["spread+impact bp/bar"] = 1e4 * net.costs.mean()
                rows.append(row)
        table = pd.DataFrame(rows).set_index("variant")
        trials = pd.DataFrame(trial)
        srs = trials.apply(lambda r: sharpe(r, BARS_PER_YEAR))
        best = srs.idxmax()
        imb = [k for k in srs.index if k.startswith("imbalance")]
        with pd.option_context("display.float_format", "{:.3f}".format, "display.width", 220):
            print(table.to_string())
        print(f"Best variant before fees: {best}. Deflated Sharpe over all {len(srs)} variants "
              f"{deflated_sharpe(trials[best], srs, periods=BARS_PER_YEAR):.3f}; within the {len(imb)} imbalance "
              f"variants {deflated_sharpe(trials[best], srs[imb], periods=BARS_PER_YEAR):.3f}")

        # why so good before fees: hit rate and the share of the mid's path the position captures
        w, lag = best_w[best]
        traded = w[sym].diff().abs().shift(lag) > 0
        print(f"Half-spread at the close of bars where {best} trades: {1e4 * touch.half_spread[traded].mean():.5f} bp, "
              f"vs {1e4 * touch.half_spread.median():.5f} bp median: the spread is not wider when the signal trades")
        held = w.shift(lag + 1)[sym]                      # traded at close t+lag, earns from t+lag to t+lag+1
        r = prices[sym].pct_change()
        moving = (held != 0) & (r != 0)
        hit = float((np.sign(held[moving]) == np.sign(r[moving])).mean())
        capture = float((held * r).sum() / r.abs().sum())
        print(f"{best}: in the market {float((held != 0).mean()):.0%} of bars; on bars where the mid moves, "
              f"right {hit:.0%} of the time; captures {capture:.0%} of the mid's total absolute path "
              f"({r.abs().sum() * 1e4:.1f} bp over {len(r) / 3600:.1f} h)")
        wf = walk_forward(prices, OrderFlowSignal, grid, train_days=1800, test_days=900, rebalance=1,
                          execution_lag=1, cost_model=fee_models[0.0], periods_per_year=BARS_PER_YEAR)
        print(f"Walk-forward (30 min train, 15 min test, lag 1 bar, spread + impact, no fee): out-of-sample net SR "
              f"{sharpe(wf.oos_returns, BARS_PER_YEAR):.2f}, mean {1e4 * wf.oos_returns.mean():.4f} bp/bar")


if __name__ == "__main__":
    cals = calibrations()
    daily_crypto(cals)
    intraday(cals)

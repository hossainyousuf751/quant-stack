"""Link D: order-book calibration mapped to backtest costs, unit by unit."""

import numpy as np
import pandas as pd
import pytest
from btlab import FlatBps, run_backtest
from lobkit import calibrate_costs, l1_features, simulate_lob, to_bars

from quantstack.adapters.costs import bar_inputs, cost_model_from_book, impact_coefficient

CAL = {"half_spread_bps": 0.5, "ofi_impact_beta": 2.0, "mean_depth": 4.0, "mid_price": 1000.0,
       "mid_vol_per_sqrt_sec": 1e-4, "volume_per_sec": 0.5}


def test_unit_conversions_by_hand():
    inp = bar_inputs(CAL, bar_seconds=3600)
    assert inp["vol"] == pytest.approx(1e-4 * 60)                   # sqrt(3600 s)
    assert inp["adv"] == pytest.approx(0.5 * 1000 * 3600)           # units/s x price x seconds
    # linear: 2.0 * 4 / 1000 = 0.008; sqrt law over 10 s: Y * 1e-4 * sqrt(10) * sqrt(4 / 5)
    assert impact_coefficient(CAL, 10) == pytest.approx(0.008 / (1e-4 * np.sqrt(10) * np.sqrt(0.8)))
    model = cost_model_from_book(CAL, 3600, capital=1e6, impact_coef=0.7)
    trade = np.array([0.1])
    want = 0.1 * 0.5e-4 + 0.7 * 0.1 * inp["vol"] * np.sqrt(0.1 * 1e6 / inp["adv"])
    assert model.cost(trade, pd.Timestamp("2024-01-01"), {"assets": pd.Index(["X"])})[0] == pytest.approx(want)


def test_per_asset_calibration_gives_per_asset_vol_and_adv():
    other = {**CAL, "volume_per_sec": 2.0, "half_spread_bps": 1.5}
    model = cost_model_from_book({"A": CAL, "B": other}, 60, capital=1e6)
    assert list(model.adv.index) == ["A", "B"] and model.adv["B"] == pytest.approx(4 * model.adv["A"])
    assert model.half_spread_bps == 1.5
    assert model.impact_coef == pytest.approx(np.mean([impact_coefficient(CAL), impact_coefficient(other)]))


def test_simulated_book_to_backtest_end_to_end():
    sim = simulate_lob(n_events=60_000, seed=2)
    cal = calibrate_costs(sim.quotes, sim.trades)
    bars = to_bars(l1_features(sim.quotes), "10s", sim.trades)
    prices = bars[["close"]].rename(columns={"close": "SIM"})
    weights = np.sign(prices.diff()).fillna(0.0)                     # a fast reversal-free toy signal
    model = cost_model_from_book(cal, bar_seconds=10, capital=1e5)
    book = run_backtest(prices, weights, rebalance=1, cost_model=model, periods_per_year=365 * 8640)
    spread_only = run_backtest(prices, weights, rebalance=1, cost_model=FlatBps(cal["half_spread_bps"]))
    assert book.costs.sum() > spread_only.costs.sum() > 0
    assert book.summary()["annual_vol"] > 0

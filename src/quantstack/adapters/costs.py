"""lobkit order-book measurements as a btlab cost model (Link D).

btlab's SpreadImpactCost charges, per unit of NAV traded in asset i,

    half_spread_bps / 1e4  +  Y * vol_i * sqrt(trade_value / ADV_i)

with vol_i the return volatility per bar, ADV_i the traded value per bar and Y the square-root-law
coefficient (Almgren et al. 2005; Toth et al. 2011). lobkit.calibrate_costs measures a recording or a
simulated book in its own units. The conversions:

    half_spread_bps   = cal["half_spread_bps"]                      already relative, in basis points
    vol per bar       = cal["mid_vol_per_sqrt_sec"] * sqrt(bar_seconds)     diffusive scaling in time
    ADV per bar       = cal["volume_per_sec"] * cal["mid_price"] * bar_seconds   units/s -> quote ccy
    Y                 matched to the measured OFI impact at a reference order size q_ref:
                      beta * q_ref / mid  =  Y * sigma_b * sqrt(q_ref / V_b)
                      beta: price change per unit of net order flow over one OFI bucket of b seconds
                      (Cont, Kukanov & Stoikov 2014); sigma_b, V_b: vol and volume over that bucket;
                      q_ref: the mean top-of-book depth, an order that just clears the best level.

The Y calibration is a modelling choice: OFI's impact is linear in flow and measured over seconds,
the square-root law is concave in size and meant for orders worked over a day. Matching them at one
size gives the right order of magnitude, not a precise coefficient; S4 reports results for a range.
Passing impact_coef (e.g. the textbook Y = 1) overrides the calibration.

Fees. An order book shows the spread and the impact, not the venue's fee schedule, which is usually
the largest cost of trading a liquid crypto pair: Binance's published base spot taker fee is 0.10%
(10 bp) per trade, against a BTCUSDT half-spread under 0.001 bp. fee_bps is charged per unit traded,
like the half-spread, so it is added to SpreadImpactCost's linear term.
Clock: calibrate_costs uses the frames' timestamps (lobkit.load_recording puts quotes and trades on
the local receive clock), so per-second rates are wall-clock rates.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd
from btlab import SpreadImpactCost

SECONDS_PER_DAY_24H = 86_400.0   # crypto trades around the clock


def impact_coefficient(cal: Mapping, ofi_bucket_seconds: float = 10.0) -> float:
    """Square-root-law Y implied by the OFI impact slope at an order of the mean top-of-book size."""
    q_ref = cal["mean_depth"]
    linear = cal["ofi_impact_beta"] * q_ref / cal["mid_price"]               # relative move for q_ref
    sigma_b = cal["mid_vol_per_sqrt_sec"] * np.sqrt(ofi_bucket_seconds)
    volume_b = cal["volume_per_sec"] * ofi_bucket_seconds
    return float(linear / (sigma_b * np.sqrt(q_ref / volume_b)))


def bar_inputs(cal: Mapping, bar_seconds: float) -> dict:
    """Vol per bar and traded value (ADV) per bar, in the units SpreadImpactCost expects."""
    return {"vol": cal["mid_vol_per_sqrt_sec"] * np.sqrt(bar_seconds),
            "adv": cal["volume_per_sec"] * cal["mid_price"] * bar_seconds}


def cost_model_from_book(cal: Mapping | Mapping[str, Mapping], bar_seconds: float, capital: float,
                         impact_coef: float | None = None, ofi_bucket_seconds: float = 10.0,
                         fee_bps: float = 0.0) -> SpreadImpactCost:
    """SpreadImpactCost from one calibrate_costs dict, or from {asset: dict} for per-asset costs.

    With several assets, half-spread and Y are taken per asset and averaged for Y (SpreadImpactCost has one
    coefficient); vol and ADV stay per asset. impact_coef overrides the calibrated Y; fee_bps (exchange fee per
    unit traded) is added to the half-spread.
    """
    per_asset = all(isinstance(v, Mapping) for v in cal.values())
    cals = dict(cal) if per_asset else {"_": cal}
    ys = [impact_coefficient(c, ofi_bucket_seconds) for c in cals.values()]
    y = float(np.mean(ys)) if impact_coef is None else impact_coef
    if not per_asset:
        inp = bar_inputs(cal, bar_seconds)
        return SpreadImpactCost(cal["half_spread_bps"] + fee_bps, y, inp["adv"], inp["vol"], capital)
    inputs = {a: bar_inputs(c, bar_seconds) for a, c in cals.items()}
    spreads = [c["half_spread_bps"] for c in cals.values()]
    # ponytail: one half-spread for all assets (SpreadImpactCost takes a scalar); the max is the cautious
    # choice. Make half_spread_bps accept a per-asset Series in btlab if spreads differ a lot.
    return SpreadImpactCost(max(spreads) + fee_bps, y, pd.Series({a: v["adv"] for a, v in inputs.items()}),
                            pd.Series({a: v["vol"] for a, v in inputs.items()}), capital)

"""sppricer notes as risklab positions (Link B).

risklab values a position by asking value(scenario) for a batch of scenarios (spot multipliers per
underlying, vol shift, skew shift, elapsed time). StructuredNotePosition answers by repricing the note
with sppricer's Monte Carlo; GridNotePosition answers from a precomputed price grid, which is what makes
thousands of VaR scenarios affordable.

Common random numbers. Every repricing uses the same seed and the same number and order of draws, so
the difference between two scenarios reflects the shock, not Monte Carlo noise. A scenario changes
only inputs (spots, vols, the schedule's distance from today), never the shape of the draw.

Elapsed time. Moving a live note forward changes its schedule and, once an observation passes, its
coupon memory and autocall state. This adapter does the conservative thing: elapsed time must be
shorter than the time to the first observation date, so the schedule only shifts closer and no state
changes. Longer horizons raise ValueError.
"""

from __future__ import annotations

from dataclasses import fields, replace

import numpy as np
from risklab import Scenario
from scipy.interpolate import RegularGridInterpolator
from sppricer import GBMModel, LocalVolModel, Market, price_mc

from quantstack.adapters.surface import SurfaceLocalVol

_SCHEDULE_FIELDS = ("observation_times", "coupon_times", "maturity")
SPOT_GRID = tuple(np.linspace(0.6, 1.4, 17))
VOL_GRID = tuple(np.linspace(-0.10, 0.15, 11))   # 2.5 vol-point steps: note prices are convex in vol


def shift_schedule(product, elapsed: float):
    """The same product seen `elapsed` years later; every date must still be in the future."""
    if elapsed == 0:
        return product
    changes = {}
    for f in fields(product):
        if f.name in _SCHEDULE_FIELDS:
            t = np.atleast_1d(np.asarray(getattr(product, f.name), dtype=float))
            if elapsed >= t[0]:
                raise ValueError(f"elapsed {elapsed:.4f}y reaches the first date {t[0]:.4f}y of {f.name}; "
                                 "observation state (memory, autocall) is not modelled, so shorten the horizon")
            shifted = t - elapsed
            changes[f.name] = float(shifted[0]) if f.name == "maturity" else tuple(shifted)
    return replace(product, **changes)


class StructuredNotePosition:
    """`quantity` units of an sppricer product, revalued by Monte Carlo in each scenario.

    Flat-vol mode (surfaces=None): GBM on `market`; vol_shift adds to each underlying's vol and
    skew_shift is not available (a flat vol has no skew). Local-vol mode: `surfaces` (volsurface,
    one per underlying, matching market.curves) drive sppricer's LocalVolModel; vol_shift and
    skew_shift reshape them with surface.shifted, which rejects shifts that create arbitrage.
    Under local vol a spot shock is sticky-strike: the surface stays put in absolute strike.
    Prices are per the product's notional; value = quantity * price.
    """

    def __init__(self, product, market: Market, quantity: float = 1.0, n_paths: int = 20_000, seed: int = 7,
                 surfaces=None, dt: float = 1 / 252):
        self.product, self.market, self.quantity = product, market, quantity
        self.n_paths, self.seed, self.surfaces, self.dt = n_paths, seed, surfaces, dt

    def price(self, spot_mult, vol_shift: float = 0.0, skew_shift: float = 0.0, elapsed: float = 0.0):
        """(price, standard error) in one market state; spot_mult has one entry per underlying."""
        m = self.market
        for i, (u, x) in enumerate(zip(m.underlyings, np.broadcast_to(spot_mult, (m.n_assets,)), strict=True)):
            m = m.with_spot(i, u.spot * float(x))
            if self.surfaces is None and vol_shift:
                m = m.with_vol(i, max(u.vol + vol_shift, 1e-4))
        if self.surfaces is None:
            if skew_shift:
                raise ValueError("skew_shift needs local-vol mode (surfaces)")
            model = GBMModel()
        else:
            surfs = self.surfaces if not (vol_shift or skew_shift) else \
                [s.shifted(vol_shift, skew_shift) for s in self.surfaces]
            model = LocalVolModel([SurfaceLocalVol(s) for s in surfs], dt=self.dt)
        res = price_mc(shift_schedule(self.product, elapsed), m, self.n_paths, seed=self.seed, model=model)
        return res.price, res.std_error

    def value(self, scenario: Scenario) -> np.ndarray:
        n = len(scenario)
        mults = np.column_stack([scenario.spot(i) * np.ones(n) for i in range(self.market.n_assets)])
        vs = np.broadcast_to(scenario.vol_shift, (n,))
        ks = np.broadcast_to(scenario.skew_shift, (n,))
        return self.quantity * np.array([self.price(mults[j], vs[j], ks[j], scenario.elapsed)[0]
                                         for j in range(n)])


class GridNotePosition:
    """A StructuredNotePosition priced from a grid over (spot multiplier per underlying, vol shift).

    The grid is computed at one horizon `elapsed` (the VaR horizon) and interpolated linearly, which is
    monotone and does not overshoot near barriers. value() of the unshocked, elapsed=0 scenario (the
    base risklab subtracts) is repriced directly, so P&L still includes time decay.
    """

    def __init__(self, position: StructuredNotePosition, elapsed: float,
                 spot_mults=SPOT_GRID, vol_shifts=VOL_GRID):
        # ponytail: linear interpolation on a fixed grid; refine near the barrier or go cubic if validate()
        # shows errors above ~2 SE where the book's tail scenarios land.
        self.position, self.elapsed = position, elapsed
        self.spot_mults, self.vol_shifts = np.asarray(spot_mults, float), np.asarray(vol_shifts, float)
        n = position.market.n_assets
        axes = [self.spot_mults] * n + [self.vol_shifts]
        prices = np.empty([len(a) for a in axes])
        for idx in np.ndindex(*prices.shape):
            prices[idx] = position.price([axes[a][i] for a, i in enumerate(idx[:n])], self.vol_shifts[idx[n]],
                                         elapsed=elapsed)[0]
        self.grid = RegularGridInterpolator(axes, prices, bounds_error=False, fill_value=None)
        self.base = position.price(np.ones(n))[0]

    def _points(self, scenario: Scenario) -> np.ndarray:
        n_assets, n = self.position.market.n_assets, len(scenario)
        cols = [scenario.spot(i) * np.ones(n) for i in range(n_assets)]
        return np.column_stack(cols + [np.broadcast_to(scenario.vol_shift, (n,))])

    def value(self, scenario: Scenario) -> np.ndarray:
        if np.any(np.asarray(scenario.skew_shift) != 0):
            raise ValueError("the price grid has no skew dimension")
        pts = self._points(scenario)
        if scenario.elapsed == 0 and np.allclose(pts[:, :-1], 1.0) and np.allclose(pts[:, -1], 0.0):
            return self.position.quantity * np.full(len(pts), self.base)
        if not np.isclose(scenario.elapsed, self.elapsed):
            raise ValueError(f"grid built for elapsed={self.elapsed}, scenario has {scenario.elapsed}")
        lo, hi = self.spot_mults[[0, -1]]
        if np.any((pts[:, :-1] < lo) | (pts[:, :-1] > hi)):
            raise ValueError(f"scenario spot multipliers leave the grid [{lo}, {hi}]")
        return self.position.quantity * self.grid(pts)

    def validate(self, n_points: int = 25, seed: int = 0) -> dict:
        """Grid vs direct Monte Carlo at random in-grid points: max |error| in price and in standard errors."""
        rng = np.random.default_rng(seed)
        n_assets = self.position.market.n_assets
        lo, hi = self.spot_mults[[0, -1]]
        pts = np.column_stack([rng.uniform(lo + 0.1, hi - 0.1, (n_points, n_assets)),
                               rng.uniform(self.vol_shifts[0], self.vol_shifts[-1], n_points)])
        direct = np.array([self.position.price(p[:-1], p[-1], elapsed=self.elapsed) for p in pts])
        err = self.grid(pts) - direct[:, 0]
        noisy = direct[:, 1] > 1e-6        # deep in or out of the money a payoff can be riskless: SE ~ 0
        in_se = np.abs(err[noisy] / direct[noisy, 1]).max() if noisy.any() else 0.0
        return {"max_abs_error": float(np.abs(err).max()), "max_error_in_se": float(in_se),
                "mean_abs_error": float(np.abs(err).mean()), "points": pts, "errors": err}

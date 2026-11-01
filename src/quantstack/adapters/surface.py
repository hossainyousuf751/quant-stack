"""volsurface surfaces as sppricer local-vol sources (Link A).

Units. sppricer simulates absolute spot levels S_t in years t and asks a source
for local_vol(K, T) at K = S_t, T = t. volsurface surfaces take the same absolute
K and T and convert internally to log-moneyness k = ln(K / F(T)) on their own
forward curve F, the curve implied from the chain by put-call parity. So no
rescaling is needed, provided the simulation starts from the curve's spot and
drifts along the same curve. local_vol_setup builds the Market that way.

Safety. Paths reach strikes far outside the quoted range, where Dupire's formula
divides by numbers near zero. The adapter evaluates local vol with volsurface's
safe path: flat in k beyond the fitted range, NaN (arbitrage) replaced by implied
vol, clipped to [floor, cap]; surface.n_clamped / n_local_vol report how often.
"""

from __future__ import annotations

import numpy as np
from sppricer import LocalVolModel, Market, Underlying
from volsurface import VolSurface


class SurfaceLocalVol:
    """A volsurface surface seen through sppricer's LocalVolSource protocol."""

    def __init__(self, surface: VolSurface, floor: float = 0.01, cap: float = 3.0):
        self.surface, self.floor, self.cap = surface, floor, cap

    @property
    def curve(self):
        return self.surface.curve

    def local_vol(self, K, T):
        return self.surface.local_vol(K, T, floor=self.floor, cap=self.cap, extrapolate="flat")

    @property
    def clamped_share(self) -> float:
        s = self.surface
        return s.n_clamped / s.n_local_vol if s.n_local_vol else 0.0


def local_vol_setup(surfaces: list[VolSurface], correlation=None, dt: float = 1 / 252,
                    names: list[str] | None = None, flat_vols=None) -> tuple[Market, LocalVolModel]:
    """(Market, LocalVolModel) whose spots and discounting come from the surfaces' own curves.

    Spot of asset i = surfaces[i].curve.spot; each asset's forward curve is its
    surface's curve (Market.curves), and discounting uses the first surface's
    curve. flat_vols, one per asset, sets the Underlying vols used by GBM on the
    same curves: the flat-vol benchmark.
    """
    names = names or [f"S{i}" for i in range(len(surfaces))]
    vols = flat_vols if flat_vols is not None else [0.2] * len(surfaces)
    market = Market(tuple(Underlying(n, s.curve.spot, v) for n, s, v in zip(names, surfaces, vols, strict=True)),
                    rate=0.0, correlation=None if correlation is None else np.asarray(correlation, dtype=float),
                    curves=tuple(s.curve for s in surfaces), discount_curve=surfaces[0].curve)
    return market, LocalVolModel([SurfaceLocalVol(s) for s in surfaces], dt=dt)

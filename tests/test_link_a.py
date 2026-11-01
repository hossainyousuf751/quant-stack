"""Link A validation: sppricer's LocalVolModel on a volsurface surface reprices the surface's own vanillas.

If local vol is wired correctly (units, forward drift, discounting, clamping), Monte Carlo prices of
European options under the local-vol paths imply back the surface's implied vols, to Monte Carlo error.
This is the test the S1 study depends on.
"""

import numpy as np
import pytest
from sppricer import EuropeanOption, price_mc
from volsurface import black_vega, fit_surface, implied_vols, synthetic_chain
from volsurface.montecarlo import simulate_local_vol

from quantstack.adapters.surface import local_vol_setup

MATURITIES = np.array([0.25, 0.5, 1.0, 2.0])
MONEYNESS = np.array([0.8, 0.9, 1.0, 1.1, 1.2])
N_PATHS = 100_000


@pytest.fixture(scope="module")
def surface():
    quotes, truth = synthetic_chain(seed=0)
    return fit_surface(quotes, truth["spot"]).ssvi_surface


def _pv(paths_at_T, K, T, curve, is_call):
    payoff = np.maximum((paths_at_T - K) if is_call else (K - paths_at_T), 0.0) * curve.discount(T)
    pair = 0.5 * (payoff[: N_PATHS // 2] + payoff[N_PATHS // 2:])        # antithetic pairs
    return pair.mean(), pair.std(ddof=1) / np.sqrt(len(pair))


def test_local_vol_mc_reprices_the_surface(surface):
    market, model = local_vol_setup([surface])
    paths = model.simulate(market, MATURITIES, N_PATHS, seed=11)[:, :, 0]
    curve, worst = surface.curve, 0.0
    for j, T in enumerate(MATURITIES):
        F, df = float(curve.forward(T)), float(curve.discount(T))
        for m in MONEYNESS:
            K, is_call = m * F, m >= 1.0                                      # out of the money
            price, se = _pv(paths[:, j], K, T, curve, is_call)
            iv_mc = float(implied_vols(np.array([price]), F, np.array([K]), T, df, np.array([is_call]))[0])
            iv_surface = float(surface.implied_vol(K, T))
            se_vol = se / float(black_vega(F, K, T, iv_surface, df))
            z = (iv_mc - iv_surface) / se_vol
            worst = max(worst, abs(z))
            assert abs(z) < 3, f"T={T} K/F={m}: MC vol {iv_mc:.5f} vs surface {iv_surface:.5f} ({z:+.1f} SE)"
    assert surface.n_local_vol > 0 and worst > 0


def test_agrees_with_volsurfaces_own_local_vol_monte_carlo(surface):
    """Two independent implementations on the same surface must agree within 4 combined SE."""
    market, model = local_vol_setup([surface])
    put = EuropeanOption(0.85 * float(surface.curve.forward(1.0)), 1.0, is_call=False)
    ours = price_mc(put, market, N_PATHS, seed=21, model=model)
    theirs_paths = simulate_local_vol([surface], np.array([1.0]), N_PATHS, seed=22)[:, 0, 0]
    theirs, theirs_se = _pv(theirs_paths, put.strike, 1.0, surface.curve, False)
    assert abs(ours.price - theirs) < 4 * np.hypot(ours.std_error, theirs_se)

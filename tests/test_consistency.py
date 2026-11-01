"""The libraries duplicate small pieces on purpose (no shared core package); these tests keep the copies in step.

Black-Scholes lives in sppricer.analytics (spot form, dividend yield), volsurface.black (forward form,
Black-76) and risklab.nonlinear._bs (spot form, no dividend yield). Two libraries load prices from yfinance.
"""

import itertools
import sys
import types

import btlab.data
import numpy as np
import pandas as pd
import pytest
import risklab.data
from risklab.nonlinear import _bs
from sppricer import bs_price
from volsurface import black_price

GRID = list(itertools.product((80.0, 100.0, 125.0), (60.0, 95.0, 100.0, 140.0), (0.05, 0.5, 3.0),
                              (0.0, 0.05), (0.08, 0.3, 0.9), (True, False)))


@pytest.mark.parametrize("q", [0.0, 0.025])
def test_sppricer_and_volsurface_black_scholes_agree(q):
    for S, K, T, r, vol, call in GRID:
        spot_form = bs_price(S, K, T, r, vol, q, call)
        fwd_form = float(black_price(S * np.exp((r - q) * T), K, T, vol, np.exp(-r * T), call))
        assert spot_form == pytest.approx(fwd_form, rel=1e-12, abs=1e-12), (S, K, T, r, vol, call)


def test_risklab_black_scholes_agrees_without_dividends():
    for S, K, T, r, vol, call in GRID:
        assert float(_bs(S, K, T, r, vol, call)) == pytest.approx(bs_price(S, K, T, r, vol, 0.0, call),
                                                                  rel=1e-12, abs=1e-12)


def test_yfinance_loaders_return_the_same_frame(monkeypatch):
    idx = pd.bdate_range("2024-01-02", periods=5)
    cols = pd.MultiIndex.from_product([["Close", "Open"], ["AAA", "BBB"]])
    raw = pd.DataFrame(np.arange(40, dtype=float).reshape(5, 8)[:, :4] + 1, index=idx, columns=cols)
    raw.iloc[0, [1, 3]] = np.nan                       # BBB not listed yet on day one
    calls = []

    def download(tickers, start=None, end=None, auto_adjust=None, progress=None):
        calls.append(auto_adjust)
        return raw

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(download=download))
    a = btlab.data.load_yfinance(["AAA", "BBB"], start="2024-01-01")
    b = risklab.data.load_yfinance(["AAA", "BBB"], start="2024-01-01")
    pd.testing.assert_frame_equal(a, b)
    assert calls == [True, True]                        # both adjust for splits and dividends
    assert list(a.columns) == ["AAA", "BBB"] and a.index.equals(idx)

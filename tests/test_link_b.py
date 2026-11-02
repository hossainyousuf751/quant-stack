"""Link B: sppricer notes valued as risklab positions, with common random numbers and a price-grid proxy."""

import numpy as np
import pytest
from risklab import Scenario, full_revaluation_var
from sppricer import BarrierReverseConvertible, Market, PhoenixAutocallable, price_mc
from volsurface import fit_surface, synthetic_chain

from quantstack.adapters.notes import GridNotePosition, StructuredNotePosition, realised_cashflows, shift_schedule
from quantstack.adapters.surface import local_vol_setup

MARKET = Market.single(100.0, 0.25, 0.03, 0.01)
NOTE = PhoenixAutocallable((100.0,), tuple(0.25 * k for k in range(1, 9)), 0.02, first_autocall_index=1)
TEN_DAYS = 10 / 252


def test_schedule_moves_closer_and_refuses_to_pass_an_observation():
    later = shift_schedule(NOTE, TEN_DAYS)
    np.testing.assert_allclose(later.observation_times, np.array(NOTE.observation_times) - TEN_DAYS)
    brc = BarrierReverseConvertible((100.0,), (0.5, 1.0), 0.03)
    assert shift_schedule(brc, 0.1).coupon_times == pytest.approx((0.4, 0.9))
    with pytest.raises(ValueError, match="first date"):
        shift_schedule(NOTE, 0.25)


def test_unshocked_value_is_the_price_and_common_random_numbers_make_it_smooth():
    pos = StructuredNotePosition(NOTE, MARKET, quantity=-2.0, n_paths=20_000, seed=5)
    assert pos.value(Scenario())[0] == -2.0 * price_mc(NOTE, MARKET, 20_000, seed=5).price
    # with independent noise (SE ~ 0.1) prices 0.1% of spot apart would not be strictly ordered
    values = pos.value(Scenario(spot_mult=np.linspace(0.97, 1.03, 13)))
    assert np.all(np.diff(values) < 0)                 # short the note: loses as spot rises (less risk-free)
    worst_of = PhoenixAutocallable((100.0, 50.0), NOTE.observation_times, 0.02, first_autocall_index=1)
    two = Market((MARKET.underlyings[0], MARKET.underlyings[0].__class__("B", 50.0, 0.3)), 0.03,
                 np.array([[1.0, 0.5], [0.5, 1.0]]))
    pos2 = StructuredNotePosition(worst_of, two, n_paths=20_000, seed=5)
    v = pos2.value(Scenario(spot_mult=np.column_stack([np.ones(5), np.linspace(0.98, 1.02, 5)])))
    assert np.all(np.diff(v) > 0)                      # long the note: B's spot only helps


def test_price_grid_matches_direct_revaluation():
    pos = StructuredNotePosition(NOTE, MARKET, n_paths=20_000, seed=3)
    grid = GridNotePosition(pos, TEN_DAYS, spot_mults=np.linspace(0.7, 1.3, 25), vol_shifts=(-0.05, 0.0, 0.05))
    check = grid.validate(n_points=8)
    assert check["max_error_in_se"] < 4, check
    scen = Scenario(spot_mult=np.array([0.85, 0.95, 1.0, 1.1]), vol_shift=np.array([0.03, 0.0, -0.02, 0.01]),
                    elapsed=TEN_DAYS)
    a = full_revaluation_var([grid], scen, alpha=0.25)["pnl"]
    b = full_revaluation_var([pos], scen, alpha=0.25)["pnl"]
    np.testing.assert_allclose(a, b, atol=4 * max(pos.price([0.85], 0.03, elapsed=TEN_DAYS)[1], 0.02))
    with pytest.raises(ValueError, match="grid built for"):
        grid.value(Scenario(spot_mult=0.9, elapsed=0.01))
    with pytest.raises(ValueError, match="leave the grid"):
        grid.value(Scenario(spot_mult=0.5, elapsed=TEN_DAYS))


def test_local_vol_mode_reacts_to_surface_shifts():
    quotes, truth = synthetic_chain(seed=0)
    surface = fit_surface(quotes, truth["spot"]).ssvi_surface
    market, _ = local_vol_setup([surface])
    note = PhoenixAutocallable((float(market.spots[0]),), (0.25, 0.5, 0.75, 1.0), 0.02, first_autocall_index=1)
    pos = StructuredNotePosition(note, market, n_paths=10_000, seed=1, surfaces=[surface], dt=1 / 52)
    base = pos.value(Scenario())[0]
    up, steeper = pos.value(Scenario(vol_shift=np.array([0.05, 0.0]), skew_shift=np.array([0.0, -0.03])))
    assert up < base and steeper < base                # the investor is short the down-and-in put
    with pytest.raises(ValueError, match="skew_shift needs"):
        StructuredNotePosition(note, market).value(Scenario(skew_shift=-0.1))


def test_realised_cashflows_follow_the_payoff_rules():
    note = PhoenixAutocallable(initial_levels=(100.0,), observation_times=(0.25, 0.5, 0.75, 1.0, 1.25),
                               coupon_rate=0.02, coupon_barrier=0.7, protection_barrier=0.6, first_autocall_index=3)
    called = realised_cashflows(note, [[90], [50], [80], [105], [120]])   # memory pays 2 coupons at t=0.75
    np.testing.assert_allclose(called, [2, 0, 4, 102, 0])
    np.testing.assert_allclose(realised_cashflows(note, [[50]] * 5), [0, 0, 0, 0, 50])  # knock-in at maturity
    # with real discounting, the cash flows reproduce the product's discounted payoff
    market = Market.single(spot=100, vol=0.2, rate=0.03)
    path = np.array([[[90], [95], [99], [98], [101]]], dtype=float)
    df = market.discount(np.asarray(note.simulation_times))
    assert realised_cashflows(note, path[0]) @ df == pytest.approx(note.discounted_payoff(path, market)[0])

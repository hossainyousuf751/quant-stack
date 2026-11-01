# quant-stack plan (Phase 0 output, awaiting approval)

Status: reconnaissance done, **no library code changed**. Section 6 lists what needs a decision.

**Decided on 2026-11-01:**
- Q1: the username is `hossainyousuf751`.
- Q2: you merge the volsurface M6 PR first, then `link/v0.2` branches from main.
- Q3: the version and release-flow proposal is approved.
- api-anything skill: skipped for now.
- Q4–Q7: your instruction was to go ahead, so the default in each applied:
  - Q4: the autocallable example moved to S1 after S1 reproduced it.
  - Q5: linear θ was not re-added.
  - Q6: all three README errors were fixed, and each figure is now printed by a script.
  - Q7: sp-pricer M6 went before M8, with the ROADMAP updated.

**Submodule setup note:** the old top-level folders were locked by the editor or OneDrive, so each repo was
cloned fresh from GitHub into `projects/` instead of being moved. Commits are identical to the ones checked in
recon. Other changes made during setup:
- `data/` folders were copied across.
- The risk-lab `v0.3.0` tag was copied across. It is local only and points at edd8b6c.
- Editable installs now point at `projects/`.
- The old folders are git-ignored. Delete them once they are no longer locked; that needs your OK.
- volsurface is pinned at `main` bd39f89, which has 37 tests. The M6 branch had 40.

---

## 1. Baseline (2026-11-01, Python 3.11.9, numpy 2.4, pandas 3.0, scipy 1.17)

| Repo | Package / version | Branch @ commit | Tags | Tests | Runtime |
|---|---|---|---|---|---|
| sp-pricer | sppricer 0.1.0 | main @ ea1943e | none | 19 passed | 3.0 s |
| volsurface | volsurface 0.1.0 | **feat/m6-put-wing @ 9e98505** (1 ahead of main bd39f89) | none | 40 passed | 23.9 s |
| backtest-lab | btlab 0.3.1 | main @ 2b1f417 | v0.3.0, v0.3.1 | 38 passed | 3.6 s |
| microstructure-lab | lobkit 0.2.2 | main @ d627f58 | v0.2.0–v0.2.2 | 31 passed | 6.6 s |
| risk-lab | risklab 0.3.0 | main @ edd8b6c | none | 36 passed, 1 skipped | 13.1 s |

All five remotes: `https://github.com/hossainyousuf751/<repo>.git`. All are pushed and clean. No library imports a
sibling in `src/` or `tests/`.

---

## 2. Verified API differences from CLAUDE.md Section 2

The code is the truth. Differences that matter for the links:

**sp-pricer**
- `Market(underlyings, rate, correlation=None)` is frozen and does not store its Cholesky factor (`simulate_gbm`
  recomputes it). `Market.single(spot, vol, rate, div_yield=0.0, name="S")`.
- Products already discount with `market.discount(t)` everywhere, so the `Curve` change only touches `Market`.
- Products take `barrier_monitoring in {"european", "continuous", "daily"}` (M4 is done). `knock_in_probability`
  applies a Brownian-bridge correction using **`market.vols`, i.e. flat vol**. This is wrong under local vol (see
  Risk R2).
- `bump_greeks(product, market, n_paths=100_000, seed=0, spot_bump=0.01, vol_bump=0.01, rate_bump=1e-4)`.
- ROADMAP: M1, M2, M4 and T1 are done. **M8 (issuer funding spread) is listed as next, ahead of M6.** The
  CHANGELOG has an Unreleased section (barrier monitoring, tooling, vega floor fix).

**volsurface**
- **The "known weakness" is already fixed on main.** M2 merged PCHIP θ(T) with θ(0)=0 and added a test that local
  vol is continuous across expiries (`test_ssvi_theta_monotone_and_local_vol_continuous_across_expiries`). There is
  **no `theta_interpolation` kwarg**, and linear θ is gone.
- `SurfaceFit` has extra fields: `essvi_*` (M4) and, on the M6 branch, `svi_af_*` (an arbitrage-free SVI that fits
  the SPX put wing) plus `local_vol_surface(min_ratio=1.5)`.
- `SSVISurface(curve, params, expiries, thetas)` accepts `SSVIParams | ESSVIParams`.
- `load_yfinance_chain` returns `(quotes, spot)`. `load_cboe_chain` returns `(quotes, spot, as_of)`.
- `ForwardCurve` is a plain class with no serialisation.
- **A local-vol Monte Carlo already exists inside volsurface:** `volsurface.montecarlo.simulate_local_vol(surfaces,
  times, n_paths, correlation, steps_per_year=252, seed, antithetic, flat_vols)`, tested at 4 SE.
  `examples/autocallable_skew.py` already prices a worst-of SPX/NDX Phoenix under eSSVI and arbitrage-free SVI
  local vol by importing `sppricer`. pyproject has the extra `pricer = ["sppricer @ git+https://...sp-pricer"]`.
  `src/` never imports sppricer, but **the extra and the example still create a library → library dependency**
  (Principle 3). See Q4.
- Saved snapshots exist locally (git-ignored): `data/SPX_20261030.csv` and `data/NDX_20261030.csv`. They are
  public CBOE delayed quotes.

**backtest-lab**
- M2–M6 are done: PBO, effective trials, factor attribution, borrow fees, walk-forward costs, and **square-root
  impact**. The full signature is
  `run_backtest(..., dollar_volume=None, capital=1e8, impact_coef=1.0, borrow_bps=0.0)`. Impact is
  `impact_coef × σ_63d × sqrt(trade × capital / ADV_20d)`, with ADV lagged one day.
- `max_drawdown(r)` and `expected_max_sharpe(n_trials, sharpe_std)` have no `periods`.
  `BacktestResult.summary()` takes no args and uses 252. `TRADING_DAYS = 252` is hard-coded in `strategies.py`.
- `check_lookahead(strategy, prices, n_cutoffs=5, seed=0, tol=1e-10) -> (bool, float)`.
- `BacktestResult` and `WalkForwardResult` are plain (not frozen) dataclasses.
- Releases go through `publish.yml`: a push to main that touches `pyproject.toml` auto-tags and **publishes to PyPI**.

**microstructure-lab**
- It has much more than listed: multi-level OFI, `MicroPrice`/`estimate_microprice`, `lead_lag`,
  `cross_venue_impact`, `simulate_as_lob`, `fill_intensity`, and Bybit recording.
- `load_recording` **replaces trade exchange time with local receive time**, so after loading, quotes and trades
  share the local clock. This is the opposite of the CLAUDE.md warning, and it is documented in the 0.2.0 CHANGELOG.
- `bucket_features` has no OHLC or volume.
- Recordings exist locally (git-ignored): `data/btcusdt_20261101_042905/` and `data/ethusdt_20261101_042905/`
  (2 h each, Binance plus Bybit), and `data/btcusdt_20261101_031854/` (~40 min).
- **Releases are release-please only**: conventional PR titles drive the version, CHANGELOG and tags, and those are
  never hand-edited (AGENTS.md). A merge to main auto-publishes to PyPI. See Q3.

**risk-lab**
- `ledoit_wolf(returns) -> (cov, delta)` is a tuple. `var_es_ewma(r, alpha, lam=0.94, warmup=500)` uses `warmup`,
  not `window`. `var_es_fhs(..., window=1000, refit_every=21)`.
- Allocators take and return `np.ndarray`, not DataFrames.
- `_bs(S, K, T, r, vol, is_call)` has **no dividend yield**.
- `Portfolio` is a non-frozen dataclass with `value(S, elapsed)` and `greeks(h)`.
  `option_portfolio_var(port, alpha, horizon_days, n_sims, seed=0) -> dict`.
- M4 (DCC-GARCH plus t-copula, `var_es_dcc`) is done. The dendrogram part of M3 was tested and rejected, as the
  README explains. **M5 is not started.**
- **37 tests, not 21.** No commit ever had 21. There is no CHANGELOG and no tags.
- `var_es_normal`, `var_es_ewma` and `var_es_fhs` lack the truncation (look-ahead) test that the repo's own
  `docs/CONVENTIONS.md` requires. I will add these during regression pinning.
- `examples/04_live_spy_and_etfs.py` Part B is confirmed as an ad-hoc monthly loop: 10 ETFs from 2007-06, a 252-day
  window, buy-and-hold within the month, no costs, no lag.

**Black-Scholes duplicates (for the consistency tests)**
- `sppricer.analytics.bs_price(spot, strike, T, rate, vol, div_yield=0, is_call)`.
- `volsurface.black.black_price(F, K, T, vol, df, is_call)` is the forward form: map `F = S e^{(r−q)T}`,
  `df = e^{−rT}`.
- `risklab.nonlinear._bs(S, K, T, r, vol, is_call)` has q = 0 only.

The grid tests cover q ≠ 0 for the first two, and q = 0 for all three.

**Data loaders**
- `btlab.data.load_yfinance(tickers, start, end, field="Close")` and `risklab.data.load_yfinance(tickers, start, end)`
  both call `yf.download(auto_adjust=True)` and `dropna(how="all")`. They agree by construction. The consistency
  test checks column, index and dtype equality on a mocked download, so it stays offline.

---

## 3. Regression numbers to pin (all reproduced exactly in Phase 0)

The pins are tests in each repo, written **before** any change. Expensive examples get `@pytest.mark.slow` tests
that call the example's functions with the same seeds. The default run stays under ~30 s.

| Repo | Source (seed) | Pinned numbers | Default or slow |
|---|---|---|---|
| sp-pricer | `examples/price_worst_of_phoenix.py` (42; 400k/200k paths) | fair 93.8767 ± 0.0660; daily 90.5834; vega −0.4359 / −0.5409 | slow (12 s); plus a fast 20k-path pin of the same product |
| volsurface | `synthetic_demo.py` (seed 7) | ρ/η/γ −0.6993/1.0019/0.3994; eSSVI ρ₀/ρ₁ −0.8373/−0.4472; RMSE 0.538 vs 0.063 | default |
| volsurface | `real_data_study.py` (local SPX/NDX csv) | ATM vols, SSVI/eSSVI params, median RMSE | slow (2.5 min), skip if data missing |
| volsurface | `autocallable_skew.py` (42, 200k) | 100.41 / 96.14 / 96.42 etc. | not pinned in volsurface (needs sppricer); pinned in quant-stack instead |
| backtest-lab | examples 01, 02, 03, 05 | e.g. best SR 0.86, DSR 0.920, PBO 0.34; survivorship 9.3% vs 12.8%; planted alpha 6.1% t 3.3; capacity table | 02/03 default, 01/05 slow |
| microstructure-lab | 01 (seed 1), 02 (seed 0), 05 | β 0.2847, R² 0.660; AS table; σ/A/k 1.077/0.588/1.389 | slow (02 is fast enough for default) |
| risk-lab | 01 (seed 1), 03 (seed 0), 02, 05 | exception counts 36/49/32/28/19; option VaR table; portfolio table; DCC table | 01/03 default, 02/05 slow |

Network-only studies (btlab 04, risklab 04, volsurface live/snapshot) are not pinned.

**Default-behaviour regression for each new hook (bit-for-bit, `assert_array_equal`):**
- `run_backtest(cost_model=None)` vs `FlatBps`.
- `TimeSeriesMomentum(vol_estimator=None)` vs the explicit rolling std.
- `price_mc(model=None)` vs `GBMModel()`.
- `Portfolio(vol_fn=None)` vs flat vol.
- `local_vol(...)` with no new kwargs vs today.

---

## 4. Changes per repo, by link (revised against the code)

### Link A: volsurface → sp-pricer

**volsurface 0.2.0**
- (a) θ interpolation is already done on main. I will **not** re-add `theta_interpolation="linear"` unless you want
  it (Q5). The stale "piecewise-linear θ jumps" comment in `tests/test_surface.py` gets fixed.
- (b) `VolSurface.local_vol(K, T, dk, dT, *, floor=None, cap=None, extrapolate=None)`. With
  `extrapolate="flat"`, k is clamped to the fitted range `[k_min, k_max]` (stored per surface from the quotes),
  which holds vol flat in k beyond it. Values are clamped to [floor, cap] and NaN goes to floor. The surface keeps
  a `clamp_count` counter attribute. All new kwargs default to None, which means today's behaviour. Afterwards,
  `montecarlo.simulate_local_vol` can use this instead of its ad-hoc `MAX_VOL`/`K_GRID`, but only if its numbers
  stay identical. Otherwise it stays as is.
- (c) `to_dict()` / `from_dict()` on `ForwardCurve` and `SSVISurface` (SSVI and eSSVI params). This is JSON-safe
  plain floats and lists, with a round-trip test to 1e-15.
- (d) `SSVISurface.shifted(parallel=0.0, skew=0.0) -> VolSurface`. It returns a thin wrapper surface:
  σ'(k,T) = σ(k,T) + parallel + skew·k, and w' = σ'²T. It calls `check_surface` and raises `ValueError` on
  arbitrage, or on σ' ≤ 0.

  Alternative considered: refitting SSVI parameters to the shifted vols. Rejected as slower and not exact.

**sp-pricer 0.2.0 (M6)**
- `Curve` protocol (`forward(T)`, `discount(T)`). `Market` gains optional keyword fields `curves:
  tuple[Curve, ...] | None = None` (one per underlying) and `discount_curve: Curve | None = None`.
  `market.discount(t)` uses `discount_curve` when it is set. Flat stays the default.
- `PathModel` protocol plus `GBMModel` (a wrapper around `simulate_gbm`, giving identical numbers).
  `price_mc(..., model=None)` and `bump_greeks(..., model=None)`.
- `LocalVolSource` protocol (`local_vol(K, T)`, `curve`). `LocalVolModel(surfaces, dt=1/252, return_grid=False)`:
  - log-Euler on a fine grid that includes the product dates;
  - forward-curve drift;
  - Cholesky correlation;
  - antithetic layout;
  - paths sampled at `times`.
- **GBM under curves:** `simulate_gbm` keeps its flat-rate drift. When `Market.curves` is set, `GBMModel` uses
  `ln F(t2)−ln F(t1)` drift. This is needed for test 3 (put-call parity under a non-flat curve).
- Tests 1–3 from CLAUDE.md use an in-test stub, plus the CRN rule: the number and order of draws depends only on
  the fine grid and n_paths, and adding an observation date that is already on the grid does not shift the stream.
- **Risk R2:** see Section 5.

**quant-stack**
- `adapters/surface.py`: `SurfaceLocalVol(surface, floor, cap)` exposes `local_vol(K, T)` (with K = S_t, so
  `k = ln(S_t / F(t))` is computed inside volsurface) and `.curve`.
- Integration test: build from `synthetic_chain`, run `LocalVolModel`, and reprice a 5 × 4 strike × maturity
  grid. MC implied vols must match the surface within 3 SE (SE converted to vol units via Black vega). As a second
  check, prices must agree with `volsurface.simulate_local_vol` within 4 combined SE.
- **S1:**
  - single-asset and two-asset (SPX/NDX) Phoenix;
  - three models: flat ATM, flat at the barrier strike, and local vol;
  - run on synthetic data, then on the saved SPX/NDX snapshot read from `projects/volsurface/data/` (skip if
    missing);
  - report fair value ± SE, issuer margin, autocall probability per date, a price-vs-barrier plot, and a dt-halving
    check;
  - cross-reference the existing volsurface `autocallable_skew` table: 100.41 → 96.14.

### Link B: sp-pricer + volsurface → risk-lab

**risk-lab 0.4.0 (M5)**
- New module `risklab/scenarios.py`:
  - `Scenario(spot_mult: ndarray, vol_shift=0.0, skew_shift=0.0, elapsed=0.0)`, frozen;
  - `Position` protocol;
  - `full_revaluation_var(positions, scenarios, alpha) -> dict(var, es, pnl)`;
  - `historical_scenarios`, `gbm_scenarios(cov, ...)` (accepts the `ledoit_wolf(...)[0]` array),
    `filtered_historical_scenarios`;
  - `stress_test(positions, named=DEFAULT_STRESSES) -> DataFrame`.
- `Portfolio` gains `vol_fn: Callable[[K, T], vol] | None = None` and `sticky: str = "strike"`, plus
  `value(scenario)` dispatch. The existing `value(S, elapsed)` is unchanged; the new code checks `isinstance` on
  `Scenario`.

  Alternative considered: a new method name. Rejected, because the CLAUDE.md protocol name is `value`.

**quant-stack**
- `adapters/notes.py`:
  - `StructuredNotePosition` uses CRN with a fixed seed;
  - it enforces the horizon: elapsed must be less than the time to the next observation date, otherwise
    `ValueError` (v1, no memory-state handling);
  - pricing-grid proxy: spot × vol per underlying, at most 2 assets, with linear interpolation;
  - validation reports max error in price and in SE at random points.
- **S2** compares delta-normal, delta-gamma-vega and grid full revaluation, adds stresses using
  `SSVISurface.shifted`, and plots P&L against spot.
- **S5** is risk-lab Study 3 with `vol_fn` from a fitted surface, comparing sticky-strike with sticky-moneyness.

### Link C: risk-lab ↔ backtest-lab

**backtest-lab 0.4.0**
- `CovarianceStrategy(estimator, allocator, window, min_history, rebalance="M")` in `strategies.py`. It computes
  only on rebalance dates and forward-fills between them. The callables take and return ndarrays (matching risklab).
  The adapter for `ledoit_wolf` is `lambda r: ledoit_wolf(r)[0]` in quant-stack.
- `TimeSeriesMomentum(vol_estimator=None)`.
- `risk_report(result, var_fn=None, alpha=0.01)` in `validation.py`.

**quant-stack**
- **S3**: synthetic (`block_covariance`) plus the 10-ETF universe (network, skip cleanly), with walk-forward,
  Deflated Sharpe across all configurations, vol vs target, turnover, cost sensitivity, FHS VaR backtests, and a
  check of the HRP turnover claim.
- Vol targeting with GARCH and EWMA as `vol_estimator`.
- risk-lab example 04 Part B gets a pointer note to S3. Nothing is deleted.

### Link D: microstructure-lab → backtest-lab

**backtest-lab 0.4.0 (same release as Link C)**
- `CostModel` protocol: `cost(trade_weights, date, context) -> per-asset fraction of NAV`.
- `FlatBps(cost_bps, slippage_bps)`. `run_backtest(..., cost_model=None)`: None keeps today's path untouched. A
  `cost_model` must not be combined with `cost_bps`, `slippage_bps` or `dollar_volume` (that raises).
- **`SpreadImpactCost(half_spread_bps, impact_coef, adv=None, vol=None, capital=1e8)` reuses the existing
  square-root formula.** A test checks that `SpreadImpactCost(half_spread_bps=5, adv=..., vol=...)` equals
  today's `run_backtest(cost_bps=5, dollar_volume=...)` to 1e-12, so there is one impact formula, not two. Without
  `adv`, it charges spread only and warns once.
- `periods_per_year`: `BacktestResult` gets a `periods_per_year: int = 252` field, used by `summary()`.
  `max_drawdown` needs none. `expected_max_sharpe` is unchanged because it is unitless.

**microstructure-lab 0.3.0**
- `analysis.calibrate_costs(quotes, trades) -> dict`. The keys are:
  - `half_spread_bps` (median of `spread / 2 / mid × 1e4`);
  - `ofi_impact_coef` (`ofi_price_impact(bucket_features(...)).beta`), with its units in the docstring;
  - `mean_depth`, `trade_size_mean`, `trade_size_median`, `trade_size_p95`;
  - `clock: "local"`.
- `features.to_bars(features, freq) -> DataFrame` with `open, high, low, close` of mid, plus `spread`, `n_updates`.

**quant-stack**
- `adapters/costs.py` maps `calibrate_costs` to `SpreadImpactCost`, with every unit conversion written out.
- **S4**: costs from the simulator and from the local Binance BTC/ETH recordings; daily crypto momentum (network,
  skip cleanly) with flat vs calibrated costs; and an intraday OFI/imbalance signal on 1 s bars through btlab with
  `check_lookahead`, lag ≥ 1 bar, Deflated Sharpe and walk-forward.

---

## 5. Risks

- **R1. Link A is half-built in volsurface already.** `simulate_local_vol` plus `autocallable_skew` duplicate
  what CLAUDE.md puts in sp-pricer plus quant-stack. I will build the sp-pricer `LocalVolModel` as specified and
  use volsurface's version as an independent cross-check in the integration test. Two implementations agreeing
  is evidence; one is not.
- **R2. Barrier bridge under local vol.** `knock_in_probability` uses flat `market.vols`. For a non-GBM model,
  v0.2 will **raise** if `barrier_monitoring != "european"`, unless the model returns the full grid, in which case
  monitoring is discrete on the grid. Pricing local vol with a silently wrong flat-vol correction is the worst
  option.
- **R3. Version numbers.** CLAUDE.md says 0.1.0 → 0.2.0, but three repos are already past that.
  - Proposed: volsurface 0.2.0, sp-pricer 0.2.0, btlab 0.4.0, lobkit 0.3.0, risklab 0.4.0.
  - risk-lab has never been tagged. I propose tagging edd8b6c as v0.3.0 locally first, so the submodule pins a
    tag.
- **R4. Auto-publishing.** btlab's and lobkit's workflows publish to PyPI on a push to main. Nothing is pushed
  without you.
- **R5. Submodule pins need pushed commits.** Locally tagged library commits work in this workspace, but a fresh
  `--recurse-submodules` clone (and quant-stack CI) fails until you push the library branches and tags.
- **R6. Moving the folders aside.** git-ignored `data/` folders must be copied into the new submodule checkouts:
  - volsurface: SPX/NDX csv, about 4 MB;
  - microstructure-lab: recordings, about 60 MB.

  volsurface also has an orphan `.git/worktrees/final` that git cannot delete (Windows permission). It is
  harmless and will not be copied.
- **R7. OneDrive.** The workspace is inside OneDrive, which sometimes locks files inside `.git` during sync. If
  git operations fail randomly, pause sync.
- **R8. Slow examples.** volsurface `autocallable_skew` (4 min) and `real_data_study` (2.5 min) and risk-lab
  02/05 (~100 s each) only appear in slow-marked tests.
- **R9. The S1 hypothesis (local vol lowers investor value) is already confirmed** by volsurface's own table
  (−3.99 at 60/70), so S1 is mostly a re-run through the new interfaces. The dt-halving and single-asset parts are
  new.

---

## 6. Open questions (Section 7 items)

- **Q1. Username:** confirm `hossainyousuf751` for submodule URLs. It is in every existing remote, but CLAUDE.md
  says to ask.
- **Q2. volsurface base:** should volsurface v0.2 branch from `main` or from `feat/m6-put-wing`?
  - M6 adds arbitrage-free SVI, PCHIP-in-T for `SVISliceSurface`, and `local_vol_surface()`. It is pushed but not
    merged.
  - Proposal: merge M6 first (your PR), then branch `link/v0.2` from main.
- **Q3. Versions and release flow (R3):**
  - Approve the proposed numbers.
  - For lobkit, I will write the `feat:` commit and leave the version and CHANGELOG to release-please, so its
    submodule pin moves only after you merge. The alternative is a hand bump, which breaks that repo's rules.
- **Q4. volsurface's `pricer` extra and `examples/autocallable_skew.py`** break Principle 3. Options:
  - (a) leave them and point the README to quant-stack S1;
  - (b) move the example into quant-stack and delete the extra (this needs your OK because it deletes a file and
    changes pyproject).

  Recommend (b) after S1 reproduces its numbers.
- **Q5. `theta_interpolation="linear"`:** linear θ was already removed in M2 and no README number depends on it.
  Recommend not re-adding it. Do you want it back anyway?
- **Q6. README errors found.** All three fixes change README text, so each needs your approval:
  - btlab README Study 3 says long-only earns "16%/yr". The actual figure is 21.4%; 16.1% is the Study 2 number.
  - lobkit README says a tick is "0.13 bp of BTC, 0.44 bp of ETH". The actual figures are 0.0013 bp and 0.044 bp.
  - volsurface README wing-RMSE numbers (7.43 → 0.27 and others) and "GBM 100.49 vs 100.51" are not produced by
    any script and do not reproduce with the obvious z-binning. Either add the script or drop the numbers.
- **Q7. sp-pricer roadmap order:** CLAUDE.md puts M6 first, but ROADMAP says M8 (funding spread) is next. I will
  do M6 and update the ROADMAP ordering in the same PR. Say so if you would rather keep M8 first.

---

## 7. Design choices made (simpler option taken, alternative noted)

- `shifted()` is a wrapper surface, not a refit (see Link A).
- `Portfolio.value(scenario)` dispatches on type rather than adding a new method.
- `SpreadImpactCost` reuses btlab's existing impact formula instead of adding a second one.
- Grid proxy interpolation is linear, not cubic, because it is monotone and has no overshoot near barriers.
  Upgrade to cubic only if validation error exceeds about 2 SE.
- Elapsed time in notes: horizon limit enforced, with no memory-state handling in v1.

---

## 8. Deviations made during the build (2026-11-01)

- **`CovarianceStrategy` schedule.** It recomputes every `every` trading days, on positions `every-1, 2·every-1, ...`,
  not at calendar month-ends.
  - A month-end schedule fails `check_lookahead`, because spotting the last trading day of a month needs
    tomorrow's date.
  - The positional schedule pairs with `run_backtest(rebalance=every, execution_lag=1)`.
- **`SpreadImpactCost` vs the existing impact path.** `SpreadImpactCost.from_dollar_volume` reproduces
  `run_backtest(dollar_volume=...)` to 1e-12, so btlab still has a single square-root impact formula.
- **Impact coefficient Y (Link D).** Y is calibrated by matching the square-root law to the measured linear OFI
  impact at an order the size of the mean top-of-book depth. The order book gives no direct estimate of Y. The
  choice is documented in `adapters/costs.py`, and `impact_coef=` overrides it.
- **risk-lab `Scenario`.** It is vectorised: one object holds a batch of shocks. A bug found in Link B (a batch
  that shocks only vols reported length 1) was fixed before release.
- **volsurface `local_vol_surface()`.** It built a new surface without `k_range`. Fixed in 0.2.0 before
  release, with a test.
- **Local-vol guard-rail counter.** sp-pricer evaluates local vol on a strike grid that spans every path, so
  volsurface's `n_clamped` counts grid points, not paths. S1 therefore also reports the share of
  (path, day) points beyond the fitted range, which is 5.7%.
- **Q4 done.** S1 reproduced volsurface's autocallable table, so the example and the `pricer` extra moved
  out of volsurface.

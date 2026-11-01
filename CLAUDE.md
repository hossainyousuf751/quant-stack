# CLAUDE.md: quant-stack, linking five quant projects into one research stack

You are working in **`quant-stack`**, the combined repository for a quantitative finance
portfolio. It contains five independent Python projects as git submodules. Your job is to
connect them so that each project makes the others better, without breaking any of them as
standalone projects.

Read this whole file before doing anything. Then follow the phases in order.

---

## 1. Context

The owner is a data analyst on a structured products desk, moving into a quant analyst role.
These repos are his public GitHub portfolio. Interviewers will read the code, so clarity,
correctness and honest reporting of results matter more than feature count.

**Hard rule:** use public or synthetic data only. Never add employer data, internal formats,
term sheets from work, or anything that resembles proprietary extraction logic.

### The combined repository: `quant-stack`

The repository that brings the five projects together is named **`quant-stack`**. Use this
name everywhere: the GitHub repo is `quant-stack`, the Python package is `quantstack`, and the
umbrella README title is "quant-stack". Its GitHub description is:

> A connected quantitative finance research stack: structured product pricing, volatility
> surfaces, honest backtesting, market microstructure and risk, linked into end-to-end studies.

`quant-stack` **contains all five projects** as git submodules under `projects/`, each pinned
to a tagged release. It also holds the integration code (adapters), the integration tests
and the cross-project studies. The five projects remain their own GitHub repositories with
their own history, CI and READMEs; the submodules are pointers to them, not copies. Cloning
`quant-stack` with `--recurse-submodules` gives a reader the whole stack in one command.

### Workspace layout

`quant-stack` is the workspace root, and this file sits at its top level.

```
quant-stack/                    the combined repo (package: quantstack)
├── CLAUDE.md                   this file
├── README.md                   umbrella README for the whole stack
├── PLAN.md, PROGRESS.md        your planning and progress log
├── pyproject.toml              depends on the five packages
├── projects/                   the five repos, as git submodules
│   ├── sp-pricer/              package: sppricer
│   ├── volsurface/             package: volsurface
│   ├── backtest-lab/           package: btlab
│   ├── microstructure-lab/     package: lobkit
│   └── risk-lab/               package: risklab
├── src/quantstack/
│   └── adapters/               surface.py, notes.py, costs.py
├── studies/                    S1-S7 cross-project study scripts
├── tests/                      consistency and integration tests
├── docs/                       plots and the draft GitHub profile README
└── .github/workflows/ci.yml    checks out submodules, runs integration tests
```

All paths below are relative to the `quant-stack/` root. When this file names a repo
(for example "risk-lab"), it means `projects/risk-lab/`.

Every repo uses a `src/` layout, `pyproject.toml`, pytest, a GitHub Actions CI workflow, an
`examples/` folder with numbered study scripts, and a README whose headline numbers come from
those scripts with fixed seeds.

---

## 2. What each repo provides today

Verify every name below against the code in Phase 0. If anything differs, the code is the
truth: update your understanding and note the difference in `PLAN.md`.

### sp-pricer (`sppricer`): structured product Monte Carlo pricing
- `Underlying(name, spot, vol, div_yield)`, `Market(underlyings, rate, correlation)`, `Market.single(...)`.
  Flat vol, flat continuously compounded rate, continuous dividend yield. `market.discount(t)`.
  Bump helpers `with_spot`, `with_vol`, `with_rate`.
- `simulate_gbm(market, times, n_paths, seed, antithetic)`: exact log steps **only on the
  product's observation dates**. Shape `(n_paths, n_times, n_assets)`. With antithetic
  sampling, the first half of paths uses Z and the second half uses −Z.
- `Product` ABC: `simulation_times` and `discounted_payoff(paths, market)`.
  Products: `EuropeanOption`, `PhoenixAutocallable` (worst-of, memory coupon, non-call
  period, European protection at maturity), `BarrierReverseConvertible` (European barrier).
- `price_mc(...) -> PricingResult(price, std_error, n_paths)`. Standard error is computed
  on antithetic pair averages.
- `bump_greeks(...) -> Greeks(price, delta, gamma, vega, rho)`: central differences with
  common random numbers. Vega is per vol point; rho is per basis point.
- `bs_price`, `bs_delta`, `bs_vega` closed forms used as test benchmarks.
- Roadmap: M3 variance reduction, M4 continuous barriers, M5 better Greeks,
  **M6 term structure plus local vol / Heston**, M7 term-sheet case studies.

### volsurface (`volsurface`): implied volatility surfaces
- `fit_surface(quotes, spot, ...) -> SurfaceFit` with `table`, `curve` (`ForwardCurve`),
  `svi_slices`, `thetas`, `ssvi_params`, `svi_surface`, `ssvi_surface`, `svi_arbitrage`,
  `ssvi_arbitrage`.
- `VolSurface.total_variance(k, T)` with `k = ln(K / F(T))`, plus `implied_vol(K, T)` and
  `local_vol(K, T, dk, dT)`. Local vol uses Gatheral's formula and returns NaN wherever the
  surface admits arbitrage.
- `ForwardCurve(spot, expiries, forwards, discounts)` with `.forward(T)` and `.discount(T)`,
  log-linear in T. Forwards and discount factors are **implied from put-call parity**.
- `FlatVolSurface`, `SVISliceSurface`, `SSVISurface`, `check_surface`,
  `synthetic_chain(...) -> (quotes, truth)`, and `volsurface.data.load_yfinance_chain`.
- **Known weakness:** `SSVISurface` interpolates θ(T) piecewise-linearly, so local vol jumps
  at every listed expiry. This must be fixed before local vol is used for pricing.

### backtest-lab (`btlab`): honest backtesting
- `Strategy` ABC: `weights(prices) -> DataFrame`. Row t is decided at the close of day t.
  Strategies: `CrossSectionalMomentum`, `TimeSeriesMomentum`.
- `run_backtest(prices, target_weights, rebalance, cost_bps, slippage_bps, execution_lag,
  delisting_return) -> BacktestResult` with `returns`, `gross_returns`, `costs`, `turnover`,
  `weights` and `.summary()`. Positions drift between rebalances; costs are flat bps on
  turnover; the universe is point-in-time.
- Metrics: `sharpe`, `sortino`, `max_drawdown`, `probabilistic_sharpe`, `deflated_sharpe`,
  `expected_max_sharpe`, `bootstrap_sharpe_ci`, all taking a `periods` argument.
- `check_lookahead(strategy, prices)` (truncation test); `walk_forward(...) -> WalkForwardResult`;
  `cost_sensitivity`; `synthetic_market`; `btlab.data.load_yfinance`.
- Roadmap: M2 Probability of Backtest Overfitting, M3 effective number of trials,
  **M4 realistic spread plus impact costs**, M5 factor attribution.

### microstructure-lab (`lobkit`): order books and market making
- `OrderBook`, `BinanceDepthSync`, `SequenceGap`; `lobkit.recorder.record_binance` and
  `load_recording`.
- `simulate_lob(...) -> SimulationResult(quotes, trades)`: a zero-intelligence book
  following Cont, Stoikov and Talreja.
- `l1_features`, `bucket_features`, `order_flow_imbalance`.
- `ofi_price_impact`, `impact_by_depth`, `predictive_r2`, `imbalance_next_move`,
  `microprice_forecast_error`.
- `ASParams`, `simulate_as`, `reservation_price`, `optimal_spread` (Avellaneda–Stoikov).

### risk-lab (`risklab`): market risk and portfolio construction
- `fit_garch` (QMLE fitted on percent returns), `garch_variance` (returns n+1 values; the
  last one is the forecast).
- `var_es_historical`, `var_es_normal`, `var_es_ewma`, `var_es_fhs`: each returns a DataFrame
  with columns `var`, `es`, `method`. These are **positive loss numbers**, and the forecast
  for day t uses only data before t.
- `backtest_var -> VaRBacktest`; `kupiec_pof`, `christoffersen_independence`,
  `traffic_light`, `acerbi_szekely_z2`.
- `sample_cov`, `ledoit_wolf` (matches scikit-learn); `equal_weight`, `inverse_variance`,
  `min_variance(long_only=)`, `risk_parity`, `hrp`, `risk_contributions`.
- `Portfolio(spot, vol, rate, shares, options=[OptionPosition(...)])` and
  `option_portfolio_var` (delta-normal, delta-gamma and full revaluation). It uses a flat
  vol and a private `_bs`.
- `simulate_garch_t`, `true_garch_t_var/es`, `block_covariance`.
- Roadmap: M3 dendrogram-aware HRP, M4 DCC-GARCH, **M5 autocallable book VaR**.
- `examples/04_live_spy_and_etfs.py` contains an ad-hoc monthly rebalancing loop that should
  be replaced by btlab's engine.

---

## 3. Architecture principles

These decisions are fixed. Do not revisit them without asking.

1. **The five repos stay independently installable and testable.** A user who clones only
   `volsurface` must be able to `pip install -e .` and pass all its tests with none of the
   other repos present.

2. **Depend on protocols, not packages.** When one library needs something another
   provides, define a small `typing.Protocol` in the consuming library and use structural
   typing. For example, sp-pricer's local vol model accepts any object with
   `local_vol(K, T)` plus a forward curve. It never imports `volsurface`. Real objects are
   wired together only in `quant-stack`.

3. **All cross-repo code lives in `quant-stack` itself**, never inside the five projects.
   `quant-stack` contains the five as submodules, plus adapters, integration tests,
   cross-repo studies and the umbrella README. Its package depends on all five.
   This keeps the dependency graph acyclic:

   ```
   volsurface   sp-pricer   backtest-lab   microstructure-lab   risk-lab
        \            |            |                |               /
         └───────────┴──── quant-stack (adapters, studies) ───────┘
   ```

   No library may depend on another library, or on `quant-stack`. Code in
   `projects/<repo>/` must never import from `quantstack` or reach outside its own folder.

4. **No shared "core" package.** The Black-Scholes code is duplicated in three places
   (`sppricer.analytics`, `volsurface.black`, `risklab.nonlinear._bs`), and three repos have
   yfinance loaders. That is acceptable for independence. Instead, `quant-stack` has
   **consistency tests** asserting the duplicates agree to 1e-12 on a grid of inputs and
   return the same data formats.

5. **Backward compatibility.** Every existing public function keeps its signature and
   default behaviour. New capability goes behind new classes, new keyword arguments with
   defaults equal to the current behaviour, or new modules. Each repo's README headline
   numbers must reproduce exactly after your changes. Add regression tests that pin them,
   using the same seeds as the examples.

6. **Version and release discipline.** Each library change gets a minor version bump
   (0.1.0 → 0.2.0), a `CHANGELOG.md` entry and a git tag, committed **inside that
   submodule's own repository**. Afterwards, update the submodule pointer in `quant-stack` to
   the tagged commit and commit that in `quant-stack` ("Bump volsurface to v0.2.0").
   - For development, install all five as editable paths:
     `pip install -e projects/volsurface` (and so on), then `pip install -e .` for `quantstack`.
   - `quant-stack` CI checks out submodules recursively and installs them from those paths,
     so the pinned submodule commits are exactly what gets tested.
   - Submodule URLs are `https://github.com/<username>/<repo>.git`. `<username>` is a
     placeholder: ask for it, and never guess.

---

## 4. The links to build

Each link lists the library changes first, then what goes in `quant-stack`, then the
definition of done. Do them in the order given in Section 5.

### Link A: volsurface → sp-pricer (local volatility pricing)

**Why:** sp-pricer prices with flat volatility. Every product in it is short a down-and-in
put, so it is highly sensitive to skew. Flat vol misprices exactly the risk these notes carry.

**volsurface v0.2 changes:**
- Replace piecewise-linear θ(T) in `SSVISurface` with a monotone, C¹ interpolation, for
  example PCHIP on θ with θ(0) = 0. Keep the old behaviour behind
  `theta_interpolation="linear"` for reproducibility. θ must stay non-decreasing, so calendar
  arbitrage is still impossible. Add a test that local vol is continuous in T across listed
  expiries.
- Add safe local-vol evaluation: `local_vol(K, T, floor=..., cap=..., extrapolate="flat")`.
  Beyond the fitted log-moneyness range, hold total-variance slope or vol flat in k. Clamp to
  [floor, cap] and record how many evaluations were clamped. The existing NaN-returning
  behaviour stays the default.
- Add `to_dict()` / `from_dict()` serialisation for `SSVISurface` and `ForwardCurve`, so a
  fitted surface (for example a saved SPX snapshot) can be loaded without refitting.
- Add `shifted(parallel=0.0, skew=0.0)`, which returns a new surface for scenario analysis.
  `parallel` adds vol points; `skew` tilts implied vol linearly in k. The result must still
  pass `check_surface`, or the method must raise.

**sp-pricer v0.2 changes (milestone M6):**
- Term structure. Introduce a `Curve` protocol (`forward(T)`, `discount(T)`) and let
  `Market` optionally accept one curve per underlying plus a discount curve. Flat rate and
  dividend remain the default; existing constructors keep working. Products must discount
  with `market.discount(t)` from the curve.
- Model abstraction. Introduce a `PathModel` protocol:
  `simulate(market, times, n_paths, seed, antithetic) -> paths`. Wrap the existing
  `simulate_gbm` as `GBMModel` (the default, giving identical numbers). Add
  `price_mc(..., model=None)`.
- `LocalVolModel(surfaces: list[LocalVolSource], dt=1/252)`:
  - Use a log-Euler scheme on a fine time grid that includes every product observation date.
  - Drift each step from the forward curve: `ln F(t+dt) − ln F(t) − ½σ²dt`.
  - Correlate Brownian increments across assets with the market's Cholesky factor.
  - Keep the antithetic layout (first half Z, second half −Z).
  - Return paths sampled at `times` only, so all existing products work unchanged.
  - Optionally return the full grid, which enables continuous barrier monitoring (M4).
  - Define the protocol `LocalVolSource` in sp-pricer: `local_vol(K, T)` plus `curve`.

**sp-pricer tests (no volsurface import; use a tiny in-test local-vol stub):**
1. A constant local vol reproduces the GBM price within 3 combined standard errors.
2. With a stub whose local vol depends on spot, the discretisation bias shrinks when dt is halved.
3. Put-call parity holds under a non-flat forward curve.

**quant-stack:**
- `adapters/surface.py` wraps a `volsurface` surface as `LocalVolSource`, converting units:
  sp-pricer works in spot S and time t, while volsurface uses k = ln(K/F(T)).
- Integration test, the key validation: build a surface from `volsurface.synthetic_chain`,
  simulate under local vol, and reprice European options on a strike × maturity grid. The
  Monte Carlo implied vols must match the surface's implied vols within 3 standard errors.
  If this fails, the local vol pipeline is wrong; do not proceed to studies.
- **Study S1, "Skew and the autocallable":** price a single-asset Phoenix and a two-asset
  worst-of Phoenix under:
  - flat ATM vol;
  - flat vol taken at the protection barrier strike;
  - local vol from the fitted SSVI surface.

  Run it on the synthetic chain, and on a saved SPX snapshot if one exists. Report fair value,
  standard error, implied issuer margin vs a 100 issue price, and autocall probability per
  date. Plot price vs barrier level for each model. Report whatever the numbers show; if local
  vol does not lower investor value relative to flat ATM vol, investigate and explain rather
  than adjusting inputs.

**Done when:** the vanilla repricing test passes, S1 runs end to end with fixed seeds, and
both repos' original README numbers are unchanged.

### Link B: sp-pricer + volsurface → risk-lab (VaR of a structured-note book)

**Why:** risk-lab's nonlinear VaR covers only Black-Scholes options with flat vol.
Structured notes are the products the owner knows professionally, so risk-lab milestone M5 is
the most compelling link for interviews.

**risk-lab v0.2 changes:**
- Define a `Position` protocol: `value(scenario) -> float | ndarray`. A `Scenario` holds
  spot multipliers per underlying, a vol shift (parallel, optionally skew), and elapsed time.
  Make the existing `Portfolio` implement it without changing its current behaviour.
- Add `full_revaluation_var(positions, scenarios, alpha) -> dict` (VaR, ES and the P&L
  vector). Add scenario generators:
  - historical: apply realised returns to today's spots;
  - Monte Carlo GBM with a covariance (accepting `ledoit_wolf` output);
  - filtered historical, rescaling historical returns by today's GARCH vol divided by
    the vol at the time.
- Add `stress_test(positions, named_scenarios) -> DataFrame` with defaults such as
  spot −10/−20/−30%, vol +5/+10 points, and spot −20% combined with vol +10.
- Let `Portfolio` accept an optional `vol_fn(K, T)` so options are valued with skew instead
  of one flat vol. Keep flat vol as the default. Support both sticky-strike and
  sticky-moneyness behaviour under spot shocks, and document the difference.

**quant-stack:**
- `adapters/notes.py`: a `StructuredNotePosition` implementing `Position` by repricing an
  sp-pricer product.
  - Use **common random numbers** (a fixed seed shared across scenarios) so scenario P&L
    is not dominated by Monte Carlo noise.
  - Elapsed time must shift the observation schedule correctly. Drop observation dates
    that have passed, and keep coupon memory state consistent; if that is too complex for
    v1, restrict scenarios to horizons shorter than the next observation date and enforce it.
  - Full revaluation over thousands of scenarios is expensive, so implement a
    **pricing-grid proxy**: precompute prices on a spot × vol grid (per underlying for
    worst-of; keep worst-of at two assets) and interpolate. Validate the grid against direct
    revaluation at random points, reporting maximum error in price and in standard errors.
- **Study S2, "Risk of a structured-note book":** a book of 3–5 Phoenix and barrier reverse
  convertible notes, optionally delta-hedged with the underlying. Compare 10-day 99% VaR and
  97.5% ES by:
  - delta-normal, using `bump_greeks`;
  - delta-gamma-vega;
  - full revaluation via the grid.

  Add stress tests including vol-surface scenarios from `surface.shifted`. Expected lesson:
  linear approximations break down near barriers. Show where, with a plot of the P&L profile
  against spot.
- **Study S5, "Skew in option VaR":** rerun risk-lab Study 3 with `vol_fn` taken from a fitted
  surface instead of flat 25%. Compare sticky-strike and sticky-moneyness VaR for the covered
  call, protective put and short straddle.

**Done when:** the grid proxy is validated, S2 and S5 run with fixed seeds, and risk-lab's
original 21 tests and README numbers are unchanged.

### Link C: risk-lab ↔ backtest-lab (risk-based portfolios under honest backtesting)

**Why:** risk-lab compares portfolio methods by exact true risk on synthetic data, but its
live ETF study uses an ad-hoc loop with no costs, lag or overfitting control. backtest-lab
has exactly that machinery.

**backtest-lab v0.2 changes:**
- Add `CovarianceStrategy(estimator: Callable, allocator: Callable, window: int,
  min_history: int)`. It is a `Strategy` that, at each date, estimates covariance from the
  trailing window of returns and allocates weights. It uses plain callables, never imports
  risklab, and must pass `check_lookahead`. Compute weights only on rebalance dates for
  speed, holding them in between; the engine already handles drift.
- Let `TimeSeriesMomentum` accept an optional `vol_estimator: Callable[[DataFrame], DataFrame]`.
  Its default must reproduce the current rolling standard deviation exactly.
- Add `risk_report(result, var_fn=None, alpha=0.01)`, a hook that runs any VaR forecaster
  on strategy returns and backtests it. It takes callables only; no risklab import.

**quant-stack:**
- **Study S3, "Risk-based portfolios under honest backtesting":** run 1/N, inverse variance,
  min-variance (sample and Ledoit–Wolf, long-only), risk parity and HRP through
  `run_backtest`, with execution lag and costs. Do it both on synthetic data (risk-lab's
  block covariance) and on the 10-ETF universe from risk-lab's live study.
  - Use walk-forward over estimation window and long-only constraint.
  - Report Deflated Sharpe across all configurations tried.
  - Report realised vol vs the target, turnover, and cost sensitivity.
  - Run FHS VaR backtests on each strategy's returns.
  - Confirm or refute risk-lab's synthetic finding that HRP turnover does not fall as the
    window grows.
- Volatility targeting: rerun backtest-lab's `TimeSeriesMomentum` with GARCH and EWMA
  forecasts from risklab as `vol_estimator`. Compare realised vol to target, and vol
  forecast errors.
- Replace the ad-hoc loop in `projects/risk-lab/examples/04_live_spy_and_etfs.py` with a note pointing
  to S3. Do not delete the file without asking.

**Done when:** S3 runs offline on synthetic data, the ETF part runs when data is available,
and backtest-lab's existing results are bit-for-bit unchanged under default settings.

### Link D: microstructure-lab → backtest-lab (costs from the order book)

**Why:** backtest-lab charges a flat bps cost, while microstructure-lab measures spreads and
price impact directly. Realistic costs are backtest-lab's milestone M4.

**backtest-lab v0.2 changes:**
- Add a `CostModel` protocol: `cost(trade_weights, date, context) -> per-asset cost`,
  as a fraction of NAV. `FlatBps(cost_bps, slippage_bps)` must reproduce today's numbers
  exactly; `run_backtest(..., cost_model=None)` keeps the current arguments working.
- Add `SpreadImpactCost(half_spread_bps, impact_coef, adv, vol)`: half-spread plus
  square-root impact, `coef × σ × sqrt(trade value / ADV)`. Volume data is optional; without
  it, fall back to spread-only and warn once.
- Make annualisation consistent for non-daily data: a `periods_per_year` argument flows into
  `summary()` and all metrics.

**microstructure-lab v0.2 changes:**
- Add `calibrate_costs(quotes, trades) -> dict` returning median relative half-spread in bps,
  OFI impact coefficient, mean top-of-book depth, and trade-size statistics. It returns a plain
  dict and never imports btlab.
- Add `to_bars(features, freq) -> DataFrame` producing mid-price bars for use by backtest-lab.

**quant-stack:**
- `adapters/costs.py` maps the `calibrate_costs` output to `SpreadImpactCost`, documenting
  every unit conversion.
- **Study S4, "Costs from the order book":**
  1. Calibrate costs from the simulated book, and from a Binance recording if one exists in
     `projects/microstructure-lab/data`.
  2. Run backtest-lab momentum on daily crypto prices (yfinance `BTC-USD`, `ETH-USD` and so on)
     under flat costs vs calibrated costs.
  3. Evaluate an intraday OFI and queue-imbalance signal on 1-second bars through btlab:
     `check_lookahead`, execution lag of one bar or more, calibrated costs, Deflated Sharpe
     across signal variants, and walk-forward.

  Expected lesson, consistent with microstructure-lab: a strong same-bucket R² does not
  survive as a tradable edge once latency and spread are included. Report the result as it
  comes out.

**Done when:** `FlatBps` regression tests pass, S4 runs offline on simulator data, and the
live parts are skipped cleanly when no recording exists.

### Link E (optional, only after A–D are done): further studies

- **S6, "How did autocallable investors actually do?":** issue a hypothetical one-year-call,
  three-year SPY Phoenix every month since 2005 using price history (btlab loader). Compute
  each note's realised IRR and compare it with its model fair value at issue. Use VIX as an
  ATM vol proxy, and state that limitation plainly.
- **S7, market-maker inventory risk:** apply risklab VaR/ES and backtests to
  Avellaneda–Stoikov P&L across risk aversion settings.
- Variance risk premium: once enough daily SPX surface snapshots exist, backtest an
  implied-minus-realised vol signal through btlab. Skip it if fewer than about 12 months of
  snapshots are available.

---

## 5. Order of work

**Phase 0: reconnaissance (no code changes).**
1. Read every repo's README, `src/`, `tests/` and `examples/`. Run every test suite and
   record pass counts and runtimes.
2. Run each example that works offline and record the headline numbers the READMEs claim.
3. Check the API map in Section 2 against the code.
4. Set up `quant-stack` as described in Section 1:
   - `git init` at the workspace root if it is not already a repository.
   - Add each of the five as a submodule under `projects/`. If they already exist as plain
     folders in the workspace and are pushed to GitHub, move them aside and re-add them from
     their GitHub URLs. If any is not on GitHub yet, stop and ask; do not create remotes yourself.
   - Create the skeleton: `pyproject.toml` for `quantstack`, `src/quantstack/`, `studies/`,
     `tests/`, `docs/` and CI.
5. Write `PLAN.md` at the root, covering:
   - the verified API differences;
   - the exact list of changes per repo, by link;
   - the regression numbers you will pin;
   - risks and open questions.
6. **Stop and ask for approval of `PLAN.md`** before changing any library.

**Phase 1: library changes, one repo at a time, in this order:**
1. volsurface
2. sp-pricer
3. backtest-lab
4. microstructure-lab
5. risk-lab

For each repo:
- Work on a branch named `link/v0.2`.
- Add regression tests pinning the current README numbers *first*, and see them pass.
- Implement the changes with tests.
- Update that repo's README: add a section on the new capability and a short "Part of
  quant-stack" note.
- Bump the version, write the changelog entry, tag `v0.2.0` locally in that submodule.
- Update the submodule pointer in `quant-stack` and commit it.

**Phase 2: `quant-stack`, in this order:**
1. Scaffolding and consistency tests (the duplicated Black-Scholes code, data formats).
2. Link A adapters and validation, then S1.
3. Link B, then S2 and S5.
4. Link C, then S3.
5. Link D, then S4.

**Phase 3: documentation.**
- `README.md` at the `quant-stack` root, titled "quant-stack", opening with the GitHub
  description from Section 1 and a table linking the five project repos: a project overview; a dependency diagram (Mermaid); a table of
  studies with headline results and plots; reproduction instructions; and one paragraph per
  study on what was surprising or went wrong and how it was diagnosed.
- A draft GitHub profile README tying the six repos together, written to
  `docs/profile_README.md` for the owner to review. It presents `quant-stack` as the
  entry point, with the five projects as its components.

---

## 6. Engineering rules

**Testing**
- Every test runs offline. Live-data studies live in `examples/` or `studies/`, skip cleanly
  when data or network is missing, and may cache snapshots under a git-ignored `data/` folder.
- Seed everything. Express Monte Carlo tolerances in standard errors (normally 3–4 SE), never
  as arbitrary absolute numbers.
- Keep each repo's unit tests under about 30 seconds and `quant-stack` integration tests
  under about 3 minutes. Mark slow tests with `@pytest.mark.slow`, excluded from the default run.
- `quant-stack` CI checks out submodules recursively, installs the five libraries from
  `projects/` at their pinned commits, and runs consistency and integration tests. Each library's own CI is unchanged and must stay green with no sibling
  installed.

**Code**
- Type hints throughout. Docstrings explain the finance and maths, not just the parameters,
  and cite papers where a method comes from one (match the existing reference style).
- Match the existing code style of each repo: frozen dataclasses, a vectorised numpy core,
  small modules.
- Do not add heavy dependencies. Allowed: numpy, scipy, pandas, matplotlib (optional extra),
  and scikit-learn in test extras only. Anything else needs approval.
- Plots follow the existing style in each repo's `plotting.py`: colourblind-friendly palette,
  differing line styles as well as colours, left-aligned bold titles, no 3D charts.

**Units and conventions, a common source of bugs. Check each one explicitly:**
- **volsurface:** k = ln(K/F(T)) and T in years. Local vol is σ(K, T) evaluated at K = S_t,
  T = t when simulating.
- **sp-pricer:** vega is per vol point and rho per basis point. Barriers are fractions of
  initial levels. Paths have shape `(n_paths, n_times, n_assets)`, in antithetic layout.
- **risklab:** VaR and ES are positive loss numbers. Forecasts on day t use data before t.
- **btlab:** weights in row t are decided at close t. `execution_lag=1` means they are traded
  at close t+1. Annualisation uses `periods` / `periods_per_year`.
- **lobkit:** timestamps are in seconds. Binance L1 uses local receive time and trades use
  exchange time; never mix them without noting it.
- **Data:** yfinance with `auto_adjust=True`. SPX options are European; ETF and stock options
  are American.

**Known pitfalls**
- **Local vol:**
  - It is only as smooth as θ(T), so fix the interpolation first.
  - It can be NaN or huge in the far wings, so clamp, extrapolate and report clamp counts.
  - Euler bias grows with dt, so include a dt-halving check in S1.
- **Common random numbers:** a scenario must never change the number or order of random
  draws, or CRN silently breaks. For example, an extra observation date must not shift the
  random stream. Test this explicitly.
- **Changing elapsed time** for a live structured note changes its schedule and memory
  state. Be conservative and enforce the horizon limit if full state handling is not
  implemented.
- **Speed:** `CovarianceStrategy` recomputing covariance daily over 12 years and 50 assets
  is slow. Compute on rebalance dates only.
- **Do not tune to the expected answer.** If a study contradicts the hypothesis stated in
  this file, first rule out bugs with targeted checks (look-ahead, units, seeds, sign
  conventions). Then report the result as it is and explain it. Earlier projects in this
  portfolio found several such surprises, and the honest write-ups are their strongest parts.

---

## 7. Boundaries: ask before doing any of these

- Changing an existing public signature or default, or deleting or loosening any existing test.
- Changing any README headline number. If a fix legitimately changes one, show the
  before and after numbers and the reason, and wait for approval.
- Pushing to any remote, creating GitHub repos (including `quant-stack` itself), or publishing tags.
- Adding a dependency not listed above.
- Downloading large datasets (anything over about 100 MB), or running anything for more than
  about 15 minutes.
- Any use of data that is not clearly public or synthetic.

## 8. How to report progress

After each phase and each link, write a short summary covering:
- what changed, per repo;
- test counts before and after;
- headline results of any new study;
- anything surprising, and how you checked it;
- what is next.

Keep a running log in `PROGRESS.md`. When unsure between two reasonable designs,
pick the simpler one, note the alternative in `PLAN.md`, and move on. Stop to ask only for
the items in Section 7.

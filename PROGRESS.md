# quant-stack progress log

## 2026-11-01: Phase 0 reconnaissance

**Done**
- Read all five repos and ran every test suite: 164 passed and 1 skipped in total, all green. Counts and runtimes
  are in `PLAN.md` §1.
- Ran every offline example. Every scripted README headline number reproduces exactly.
- Found three README prose errors, none produced by a script (PLAN Q6).
- Checked the CLAUDE.md API map against the code. The differences are in PLAN §2. The largest are:
  - volsurface already has smooth θ and a local-vol Monte Carlo;
  - btlab already has square-root impact;
  - risk-lab has 37 tests, not 21;
  - lobkit releases through release-please.
- Wrote `PLAN.md`.

- Q1–Q3 answered; see the PLAN header.
- Set up quant-stack: ran `git init`, added the five submodules from GitHub under `projects/`, and created the
  skeleton:
  - `pyproject.toml`
  - `src/quantstack`
  - a smoke test, 5 passed
  - CI
- Re-ran each library suite from the submodules. All green:
  - sp-pricer: 19 passed
  - volsurface (main): 37 passed
  - btlab: 38 passed
  - lobkit: 31 passed
  - risklab: 36 passed, 1 skipped
- Skills:
  - ponytail is active and graphify is installed.
  - agentskill skill installed. Its CLI needs cargo, which is not installed.
  - api-anything was skipped.

**Not done yet**
- No library code has been changed.
- The old top-level folders are still on disk, locked and git-ignored.

**Next**
- Approval of PLAN.md and answers to Q4–Q7.
- You merge volsurface M6, then I pin it.
- Build the graphify graph over `projects/`.
- Phase 1, starting with volsurface.

## 2026-11-01: Phase 1, library changes (all local; nothing pushed)

| Repo | Version / tag | Tests before → after (default; slow) | Changes |
|---|---|---|---|
| volsurface | 0.2.0, `v0.2.0` | 40 → 46; +2 slow | `local_vol(floor=, cap=, extrapolate="flat")` with clamp counts, `k_range`, `to_dict`/`from_dict`, `shifted()` / `ShiftedSurface` |
| sp-pricer | 0.2.0, `v0.2.0` | 19 → 28; +1 slow | `Curve`, `Market(curves=, discount_curve=)`, `PathModel`, `GBMModel`, `LocalVolSource`, `LocalVolModel`, `price_mc(model=)` |
| backtest-lab | 0.4.0, `v0.4.0` | 38 → 48; +1 slow | `CostModel`/`FlatBps`/`SpreadImpactCost`, `periods_per_year`, `CovarianceStrategy`, `TimeSeriesMomentum(vol_estimator=)`, `risk_report` |
| microstructure-lab | `feat:` commit; release-please tags 0.3.0 on merge | 31 → 38 | `calibrate_costs`, `to_bars` |
| risk-lab | 0.4.0, `v0.4.0` (plus `v0.3.0` retro-tag) | 37 → 49 (incl. 1 skip); +2 slow | `scenarios` module (M5), `Portfolio(vol_fn=, sticky=, underlying=)`, missing look-ahead tests |

**Notes**
- Each repo's README numbers were pinned in tests before any code changed, and every pin still passes.
- Default paths are unchanged; the new hooks are checked against the old code paths.
- No library imports a sibling or `quantstack`. The one exception is volsurface `examples/autocallable_skew.py`
  (Q4), which moves to quant-stack after S1.
- volsurface `main` was fast-forwarded locally to the M6 commit (9e98505), because the GitHub merge had not
  happened.

**README fixes (Q6)**
- btlab: long-only raw return is 21%, not 16%. Example 03 now prints it.
- lobkit: a tick is 0.0013 / 0.044 bp, not 0.13 / 0.44. Example 04 now prints it.
- volsurface: the wing-band RMSE figures are now printed by `real_data_study.py`, defined as z = k/√w. That
  run found "0.15" should be "0.16".

**Surprises**
- `check_lookahead` rejects a calendar month-end schedule, because spotting the last trading day of a month
  needs tomorrow's date. `CovarianceStrategy` therefore recomputes on positions `every-1, 2·every-1, ...`,
  which pairs with `run_backtest(rebalance=every, execution_lag=1)`.
- sp-pricer's barrier bridge assumes flat vol, so `price_mc` raises for non-European monitoring under
  `LocalVolModel`.
- Euler bias at dt = 1/2, 1/4 and 1/8 for a steep-skew stub: −0.59, −0.18 and −0.03 per 100.

**Next:** Phase 2 in quant-stack: consistency tests, then Links A, B, C, D and their studies.

## 2026-11-01/02: Phase 2 (integration and studies) and Phase 3 (documentation)

**quant-stack**
- `adapters/surface.py` (Link A), `adapters/notes.py` (Link B: CRN repricing, horizon guard, validated price
  grid), `adapters/costs.py` (Link D: every unit conversion documented, plus fees).
- Tests: 18 (consistency, Links A, B, D, smoke). All pass on current and on the oldest supported numpy, pandas
  and scipy.
- Studies S1–S5 run end to end with fixed seeds. Tables are in `docs/s*_output.txt`, alongside the plots.
- `README.md` (umbrella) and `docs/profile_README.md` (draft for your GitHub profile).
- graphify code graph in `graphify-out/` (git-ignored): 1,731 nodes.

**Library follow-ups found while integrating.** The tags below were moved, which is safe because nothing is
pushed.
- risk-lab: `Scenario` length for vol-only batches (bug, now tested).
- volsurface: `local_vol_surface()` drops `k_range` (now tested). The autocallable example moved to S1 and
  the `pricer` extra was removed.
- volsurface and risk-lab: the regression pins were too tight across supported scipy versions. They are now
  held at the precision the README prints; see each test module's docstring.

**Headline results.** Full write-up in the README section "What was surprising".
- S1: local vol lowers the SPX/NDX worst-of note by 4.00 ± 0.04 per 100. This reproduces volsurface's
  independent simulator. A flat vol taken at the barrier strike overshoots the effect.
- S2: delta-normal VaR of the hedged book is 0, against 90 under full revaluation. Delta-gamma-vega
  overstates it at 152, because the notes' value is concave in vol (checked by repricing).
- S3: long-only minimum variance has the lowest true risk after lag and costs (DSR 0.94). HRP turnover
  barely falls with the window on synthetic data but falls 4× on ETFs. FHS VaR under-predicts on ETFs.
- S4: OFI fails after spread. Queue imbalance survives spread, latency and book walking, but its break-even
  fee is about 0.2–0.3 bp, so any exchange taker fee kills it.
- S5: sticky moneyness more than doubles a short straddle's 1-day VaR against sticky strike.

**Test counts at the end** (default; slow in brackets):

| Repo | Tests |
|---|---|
| sp-pricer | 28 (+1) |
| volsurface | 47 (+2) |
| backtest-lab | 48 (+1) |
| microstructure-lab | 38 |
| risk-lab | 49, 1 skipped (+2) |
| quant-stack | 18 |

**Not done, needs you:**
- Deleting the old top-level folders (`/sp-pricer` and the others), which were locked during setup and are
  git-ignored.

## 2026-11-02: Releases, pushed one repo at a time

Each library was merged by PR. CI on `main` was checked before the next one started, and quant-stack was
re-pinned to the released commit.

| Repo | PR | Release | Pinned commit | Checks |
|---|---|---|---|---|
| volsurface | #6, merge | `v0.2.0` | 132c38c | `main` CI green |
| sp-pricer | #1, merge | `v0.2.0` | 95fafc6 | `main` CI green |
| risk-lab | #1, merge | `v0.3.0`, `v0.4.0` | 05fd489 | `main` CI green |
| backtest-lab | #9, merge | `v0.4.0`, tagged by publish.yml | c5dce70 | PyPI btlab 0.4.0 installs |
| microstructure-lab | #10, squash | `v0.3.0`, tagged by release-please | 91b9feb | PyPI lobkit 0.3.0 installs |

- backtest-lab: CI on pytest 8.3 and later rejected `pytest.approx` on a nested dict. Fixed with `==` before
  merging.
- microstructure-lab: the squash commit's tree matches the tested branch exactly. The release commit
  changes only the version, manifest and changelog. The two failed runs on the release PR started no jobs:
  the bot merged the PR and deleted its branch first. The 0.2.2 release shows the same pattern.

## 2026-11-02: Tidy-ups and Study S6 (Link E)

**Tidy-ups.**
- Deleted the merged `link/v0.2` branches on sp-pricer, volsurface, backtest-lab and risk-lab. microstructure-lab
  keeps its branch: after the squash merge, it is the only ref holding df1d49a, which older quant-stack commits pin.
  Every commit quant-stack has ever pinned was checked as still fetchable.
- Deleted the old top-level folders after checking: no unpushed commits, stashes or changes, and data identical to
  `projects/`.
- quant-stack, sp-pricer, volsurface and risk-lab moved to actions/checkout and setup-python v7 (Node 20 deprecation),
  each by PR, with CI green on the branch and on `main`.
- GitHub topics on all six repos.

**S6, "How did autocallable investors actually do?"**
- New adapter `realised_cashflows(product, levels)` in `adapters/notes.py`. It reads a note's cash flows on a realised
  path from the product's own payoff, by discounting one date at a time, and has a test.
- 250 monthly SPY Phoenix notes, 2005-01 to 2025-10, with the coupon set at issue for a fair value of 98. Realised
  PV is 101.20, or +3.20 ± 0.72 (Newey-West). That is +2.28 ± 0.38 without the 2008, 2009 and 2020 vintages.
  94% autocalled and none lost capital; the lowest maturity level was 72%.
- Checks:
  - The coupon solve is exact under common random numbers, asserted to 1e-9.
  - The payoff code agrees with the study on when each note ended.
  - The output is deterministic, and the study skips cleanly offline.
- A first version used a fixed 8% coupon, giving fair values up to 112. That is unrealistic, so it is kept only as
  a secondary comparison.
- 13 issues in 2013–2016 have a negative par coupon because there is no funding spread and the note is on total
  return. This is reported, not hidden.
- A README claim that 2000 issues would have lost capital was checked against data and was wrong: they end at
  60–85%, and April 2000 matures at 60.4%. Corrected.
- quant-stack tests: 18 → 19.

## 2026-11-02: Study S7, market-maker inventory risk (Link E)

- **Setup:** `studies/s7_market_maker_risk.py` runs the Avellaneda–Stoikov quoter in lobkit's order book: 2,500
  sessions of 5 minutes for γ ∈ {0.001, 0.005, 0.02} × {inventory, symmetric}. risk-lab measures session P&L
  tails and backtests four VaR models on sessions 1,001–2,500. It runs offline in about 7 minutes.
- **Tails:** in the paper's fill model no session loses money. In the book, γ = 0.005 inventory has the best
  mean/ES (1.90). Symmetric quotes earn 46–65% more with 5–13× the ES.
- **Backtests:**
  - Historical passes 6 of 6 and FHS 5 of 6 (one rejection at p = 0.032, in line with 24 tests).
  - Normal fails 4 of 6, and its ES is rejected by Z2 on 4 books.
  - EWMA has 0 exceptions on every inventory book: it assumes zero-mean P&L, so it overstates VaR 2.6–5.7×.
- **Checks:**
  - risk-lab VaR models across input units: exact for three; FHS moves the mean VaR by 0.1% (GARCH optima).
  - The first 200 sessions reproduce microstructure-lab's README row exactly.
- **Finding for microstructure-lab, not acted on (needs approval):** its γ = 0.005 inventory mean of 19.4
  (seeds 0–199) is a low draw. 2,500 sessions give 22.6 ± 0.26, and fresh seed blocks give 21.3–24.1. Inventory
  control costs 32–40% of mean P&L, not 33–45%.

## 2026-11-11: PyPI releases

Three PyPI names were taken by unrelated projects: `quantstack`, `volsurface` and `risklab`. The look-alikes
`quant-stack` and `risk-lab` would be rejected too. The owner chose new distribution names; the import names
are unchanged.

| Repo | PyPI | Release | Checks |
|---|---|---|---|
| sp-pricer | `sppricer` | v0.2.1 (adds the MIT licence the repo lacked) | PyPI install: 28 passed |
| volsurface | `volsurface-lab` | v0.2.1 | PyPI install: 47 passed |
| risk-lab | `marketrisk-lab` | v0.4.1 | PyPI install: 50 passed |
| quant-stack | `quantstack-lab` | v0.1.0 (adds the MIT licence it declared) | wheel + five libraries from PyPI: 14 passed, 5 submodule guards skipped |

None of the library releases change any code. Each uses backtest-lab's `publish.yml` with trusted
publishing. The quant-stack pins renamed each dependency in the same commit, so pip never resolves a name
to the unrelated package.

Caught on the way:
- `dist/` was committed in the volsurface PR. It was amended out, and `dist/` and `build/` were ignored
  there and here.
- A `grep -c $'\r'` line-ending check gave false readings. Rechecked on raw bytes: every file is LF.
- Stale `volsurface`/`risklab` registrations from old editable installs were removed locally.
- PyPI allows only 3 pending publishers at once, so `quantstack-lab` was registered after the libraries
  published.

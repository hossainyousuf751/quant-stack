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
- Pushing (see below).
- Deleting the old top-level folders (`/sp-pricer` and the others), which were locked during setup and are
  git-ignored.

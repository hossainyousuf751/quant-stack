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

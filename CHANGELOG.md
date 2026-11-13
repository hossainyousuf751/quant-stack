# Changelog

## Unreleased

- Study S8: issuers' published estimated value against quant-stack fair value, on real notes, with terms
  hand-entered from SEC filings (`studies/s8_notes/`).

- Allow sppricer 0.3 and 0.4 (likelihood-ratio Greeks; callable dates via `autocall_indices`; no change
  to prices). The repo pins sp-pricer v0.4.0.

## 0.1.1 (2026-11-14)

No code changes to the adapters.
- README: a tested Quick start (surface → local-vol price → VaR) using the PyPI packages only, so the
  PyPI page shows how to use the package.
- Pinned microstructure-lab v0.3.1 (lobkit 0.3.1, docs only: Study 4 rerun with 2,500 episodes per row).
- A weekly `pypi-install` workflow installs the latest release from PyPI and runs its own tests.

## 0.1.0 (2026-11-11)

First release on PyPI, as `quantstack-lab` (`pip install quantstack-lab`; the import is `quantstack`). The
name `quantstack` on PyPI belongs to an unrelated project.

- Adapters that wire the five libraries together through their protocols:
  - `adapters.surface`: volsurface surfaces as sp-pricer local-vol sources;
  - `adapters.notes`: sp-pricer notes as risk-lab positions, with a validated price-grid proxy and
    `realised_cashflows`;
  - `adapters.costs`: microstructure-lab cost calibration as btlab cost models.
- Depends on the five libraries from PyPI: `sppricer`, `volsurface-lab`, `btlab`, `lobkit` and
  `marketrisk-lab`. Each is capped below its next minor version.
- Studies S1–S7, the consistency and integration tests, and the plots live in the repository, not the package.

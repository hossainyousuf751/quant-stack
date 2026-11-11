# Changelog

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

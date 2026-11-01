# quant-stack

> A connected quantitative finance research stack: structured product pricing, volatility
> surfaces, honest backtesting, market microstructure and risk, linked into end-to-end studies.

quant-stack holds five independent libraries as git submodules, pinned to tagged releases. It
connects them through small adapters and runs cross-project studies on top. No library imports
another, and none imports quant-stack. Each still installs, tests and releases on its own.

| Project | Package | What it does |
|---|---|---|
| [sp-pricer](https://github.com/hossainyousuf751/sp-pricer) | `sppricer` | Monte Carlo pricing of Phoenix autocallables and reverse convertibles, Greeks, barrier monitoring; Dupire local vol and term structure from v0.2 |
| [volsurface](https://github.com/hossainyousuf751/volsurface) | `volsurface` | Arbitrage-free implied vol surfaces (SVI, SSVI, eSSVI, arbitrage-free SVI) from raw quotes, Dupire local vol, scenario shifts |
| [backtest-lab](https://github.com/hossainyousuf751/backtest-lab) | `btlab` | Backtesting with look-ahead tests, Deflated Sharpe, PBO, walk-forward, pluggable cost models, covariance strategies |
| [microstructure-lab](https://github.com/hossainyousuf751/microstructure-lab) | `lobkit` | Order-book reconstruction, order-flow imbalance, micro-price, Avellaneda–Stoikov; cost calibration and bars |
| [risk-lab](https://github.com/hossainyousuf751/risk-lab) | `risklab` | VaR/ES models and backtests, DCC-GARCH, shrinkage, HRP; scenario full-revaluation VaR and stress tests |

## How the pieces connect

```mermaid
flowchart LR
    VS[volsurface] -->|"local_vol(K, T), curve<br/>adapters/surface.py"| SP[sp-pricer]
    SP -->|"value(scenario)<br/>adapters/notes.py"| RL[risk-lab]
    VS -->|"shifted surfaces, vol_fn"| RL
    RL -->|"estimators and allocators<br/>(plain callables)"| BT[backtest-lab]
    MS[microstructure-lab] -->|"calibrate_costs to SpreadImpactCost<br/>adapters/costs.py"| BT
    subgraph quant-stack
      A[adapters, studies S1-S5, integration tests]
    end
```

Every arrow is a **protocol, not an import**. The library on the receiving end of an arrow defines a
small interface:

- sp-pricer's `LocalVolSource` is anything with `local_vol(K, T)` and a `curve`.
- risk-lab's `Position` is anything with `value(scenario)`.
- btlab's `CostModel` is anything with `cost(trade, date, context)`.

quant-stack wires real objects into those interfaces in [`src/quantstack/adapters/`](src/quantstack/adapters), and
nowhere else.

The libraries also duplicate a few small pieces on purpose instead of sharing a core package: three
Black-Scholes implementations and two yfinance loaders. [`tests/test_consistency.py`](tests/test_consistency.py)
asserts that the duplicates agree to 1e-12 on a grid of inputs and return the same data format.

## Studies

| Study | Question | Headline result |
|---|---|---|
| [S1](studies/s1_skew_autocallable.py) skew and the autocallable | What does pricing off the smile do to a Phoenix? | On the 2026-10-30 SPX/NDX close, local vol lowers the worst-of note from 100.44 to 96.44 per 100 (−4.00 ± 0.04 SE). The synthetic notes fall by 3.4 and 5.8 |
| [S2](studies/s2_note_book_risk.py) risk of a structured-note book | Where do linear VaR approximations break? | Delta-normal VaR of the delta-hedged book is 0, against 90 under full revaluation. Delta-gamma-vega overstates it at 152 |
| [S3](studies/s3_risk_portfolios_backtest.py) risk-based portfolios, honestly backtested | Do risk-lab's rankings survive costs, lag and selection? | Long-only minimum variance keeps the lowest true risk (9.5% vs 15.1% for 1/N) after lag and costs. Best of 24 configurations: Deflated Sharpe 0.94, walk-forward out-of-sample Sharpe 0.59. HRP's turnover barely falls with the window on synthetic data but falls 4× on real ETFs |
| [S4](studies/s4_costs_from_order_book.py) costs from the order book | Does a strong same-second order-flow relationship survive as a trade? | OFI (R² 0.59) loses after the spread alone. Queue imbalance survives spread, 1–5 s latency and the recorded book at small size, but covers at most 0.24 bp per unit traded, so any exchange taker fee kills it |
| [S5](studies/s5_skew_option_var.py) skew in option VaR | How much does the smile's behaviour under spot moves change option VaR? | Sticky moneyness more than doubles a short straddle's 1-day VaR against sticky strike (0.82 vs 0.38 synthetic, 0.84 vs 0.32 SPX) |

Each study prints its tables to [`docs/`](docs) (`s*_output.txt`, plus plots). All seeds are fixed.

### S1: skew and the autocallable

![Price vs barrier](docs/s1_price_vs_barrier_spx.png)

The note is sp-pricer's README note: 3 years, quarterly, a 2% memory coupon, autocall at 100% from
year 1, and 60% European protection. Every product here is short a down-and-in put, so the put skew
drives its value. Three models price the same note on the same forward curves and random numbers:

| SPX/NDX worst-of, ρ = 0.9 | Fair value | vs flat ATM | P(autocall at year 1) | P(knocked in) |
|---|---|---|---|---|
| flat ATM vol (18.2% / 23.8%) | 100.44 | | 47.0% | 7.7% |
| flat vol at the 60% strike | 94.15 | −6.29 ± 0.04 | 42.4% | 17.7% |
| Dupire local vol (arbitrage-free SVI) | **96.44** | **−4.00 ± 0.04** | 57.4% | 11.2% |

The local-vol pipeline is validated first, in [`tests/test_link_a.py`](tests/test_link_a.py). Monte
Carlo prices of 20 vanillas under sp-pricer's `LocalVolModel` imply back the volsurface surface's
own vols within 2.5 standard errors. Flat ATM vol misses the same targets by up to 940.

The S1 numbers also reproduce volsurface's earlier, independent simulator: 100.41, 96.14 and 96.42.
Halving or doubling the time step moves the worst-of note by no more than its standard error (96.23,
96.30 and 96.15, each ± 0.07).

### S2: risk of a structured-note book

![P&L profile](docs/s2_pnl_profile.png)

A dealer is short four notes on two underlyings and may delta-hedge with shares. Each method gives a
10-day 99% VaR (lognormal scenarios, with implied vol falling 0.8 points per 1% rise in A):

| Book | Delta-normal | Delta-gamma-vega | Full revaluation (price grid) |
|---|---|---|---|
| unhedged | 89.9 | 222.4 | 154.4 |
| delta-hedged | **0.0** | 152.2 | **90.0** |

Full revaluation reprices every note in every scenario. To make 20,000 scenarios affordable, it
interpolates on a price grid validated against direct repricing at random points: the mean error is
0.02 per 100 and the largest is 2.2 Monte Carlo standard errors.
The same pattern holds under fat-tailed DCC-t scenarios.

### S5: skew in option VaR

risk-lab Study 3's books, priced off a fitted smile instead of one flat vol, with full revaluation only:

| 1-day 99% VaR | flat ATM | sticky strike | sticky moneyness |
|---|---|---|---|
| covered call | 1.97 | 2.05 | 1.92 |
| protective put | 1.86 | 1.83 | 2.04 |
| short ATM straddle | 0.38 | 0.38 | **0.82** |

(Synthetic SSVI surface; the SPX snapshot gives the same ordering.)

## What was surprising, what went wrong, and how it was diagnosed

**S1: a "skew-aware" flat vol overshoots.** Pricing the note with flat vol taken at the barrier
strike sounds like a cheap way to respect the skew, so I expected it to land near local vol. It lands
well below it instead: −6.3 against −4.0 on SPX/NDX, and −8.1 against −5.8 on the synthetic worst-of.
The autocall probabilities show why. A barrier-strike vol applies put-wing volatility everywhere,
including near and above 100%, where local vol is low. So it understates the chance of an early
call at year 1 (42% vs 57%) and overstates the chance of ending knocked in (18% vs 11%). Local vol
is not "flat vol at the right strike"; it is a different vol in each region the path visits. The
local-vol pipeline was validated before any of this: Monte Carlo vanillas reprice the surface within
2.5 SE, and two independent simulators agree within error.

**S2: delta-gamma-vega was worse than delta-normal, in the other direction.** I expected the
second-order expansion to land between delta-normal and full revaluation. Instead it overstates the
unhedged book's VaR by 44% (222 vs 154). To find out why, I repriced each note under parallel vol
shifts. The notes' value is concave in vol: an 8-point fall in vol raises the single-asset Phoenix by
3.8 per 100, while vega × shift says 4.9. The scenarios move vol against spot (−0.8 points per 1%),
so the 10-day tail combines a rally with a large vol fall, exactly where linear vega overstates the
dealer's loss. Delta-normal misses the other way: it reports zero risk for the delta-hedged book,
which full revaluation puts at 90. Getting the full-revaluation number cheaply also took a second
attempt. The first price grid missed direct repricing by up to 5.5 SE. That pointed at the vol axis
rather than the spot axis, because tightening the spot spacing made no difference. Halving the vol
step brought the worst point to 2.2 SE, and the VaR itself moved by only 2%.

**S3: one finding confirmed, one refuted, one bug of my own.** On risk-lab's synthetic data, HRP's
turnover barely falls as the estimation window grows (4.4 to 3.3 times a year, while minimum variance
falls from 5.6 to 1.0), confirming risk-lab's result under a real backtest. On the 10 ETFs it falls
4×, from 3.6 to 0.9. The block covariance's equal within-block correlations make HRP's ordering flip
between near-ties, while stocks, bonds and commodities form stable clusters. FHS VaR, which passes
every backtest on synthetic data, takes 44–53 exceptions against 37 expected on the ETF portfolios.
A first run also reported "true" volatility well below realised volatility for every method. The
cause was in my study code: it averaged in the warm-up rebalances that hold nothing. 24 empty
rebalances out of 144 explained the gap exactly (12.6% vs 15.1% for 1/N).

**S4: the edge that should not have survived, and what finally killed it.** The expected lesson was
that a strong same-second relationship (OFI explains 59% of BTC's one-second mid changes) does not
survive latency and spread. For OFI itself that holds: it trades about 2,000 times an hour, and the
spread alone costs more than its gross edge, so its net Sharpe is negative at every lag. Queue
imbalance did survive: positive net of spread and calibrated impact at lags of 1, 2 and 5 seconds,
right on 90% of the mid's moves. I treated that as a bug until each candidate was ruled out:

- The look-ahead check rebuilds features from quotes truncated at each cutoff, and it passes.
- The spread at the trades' execution bars equals the median spread, so the edge is not a wide
  spread being ignored.
- Walking each trade through the recorded 10-level book at $100,000 cuts BTC's edge by a third but
  leaves it positive. On the thinner ETH book the same size turns every variant negative; at $1,000
  both survive.

What kills it is the cost an order book does not show: exchange fees. The signal's gross edge
covers at most about 0.24 bp per unit traded on BTC and on ETH, against Binance's
published base taker fee of 10 bp. At any taker fee, every variant loses. A queue-imbalance edge
belongs to whoever is paid to provide liquidity, not to whoever takes it. Two hours of data is one
sample, so this is an illustration of the method rather than a result to trade on.

**Testing across versions.** The libraries promise numpy ≥ 1.24, pandas ≥ 2.0 and scipy ≥ 1.10. I
ran every suite in an environment with exactly those versions. Every test passed except my new
regression pins: optimiser-fitted values move by up to 1e-5 relative between scipy 1.10 and 1.17,
and one penalised SVI fit settles on a different optimum (0.1815 vs 0.1790, both printed as 0.18).
The pins now hold each figure to the precision the README actually prints.

## Reproduce

```bash
git clone --recurse-submodules https://github.com/hossainyousuf751/quant-stack.git
cd quant-stack
for p in sp-pricer volsurface backtest-lab microstructure-lab risk-lab; do pip install -e "projects/$p"; done
pip install -e ".[dev]"
pytest                                   # consistency and integration tests, offline, about 1 minute
python studies/s1_skew_autocallable.py   # each study writes docs/s*_output.txt-style tables and plots
```

What the studies need:

- **S1 and S5** use volsurface's saved CBOE snapshot (`projects/volsurface/data/`, git-ignored; create it with
  `projects/volsurface/examples/snapshot.py`) for their real-data parts, and skip those parts without it.
- **S4** uses microstructure-lab's Binance recordings, likewise git-ignored and created with its recorder.
- **S3 and S4** download Yahoo Finance prices on first run and cache them in `data/`. They skip those parts
  when offline.

Each library's own tests still run without the others installed: `cd projects/<repo> && pytest`.

## Layout

```
quant-stack/
├── projects/          the five libraries (git submodules, tagged releases)
├── src/quantstack/
│   └── adapters/      surface.py (Link A), notes.py (Link B), costs.py (Link D)
├── studies/           S1-S5
├── tests/             consistency and integration tests
└── docs/              study outputs and plots; profile_README.md
```

Data is public or synthetic only: Yahoo Finance, CBOE delayed quotes, Binance public market data,
and simulators.

# Hi, I'm Yousuf

I work on a structured products desk as a data analyst and am moving into quantitative analysis.
These repositories are where I build the models behind that work from scratch, using public or
synthetic data only, and test them honestly.

## Start here: [quant-stack](https://github.com/hossainyousuf751/quant-stack)

quant-stack is a connected quantitative finance research stack: structured product pricing,
volatility surfaces, honest backtesting, market microstructure and risk, linked into end-to-end studies.
It holds the five libraries below as git submodules and wires them together in cross-project
studies. No library imports another: each depends only on numpy, scipy and pandas, and passes its own
tests on its own.

| Library | What it does | One result |
|---|---|---|
| [sp-pricer](https://github.com/hossainyousuf751/sp-pricer) | Monte Carlo pricing of autocallables and reverse convertibles, Greeks, barrier monitoring, Dupire local vol | A 3-year worst-of Phoenix is worth 93.88 per 100 under flat vol, so the implied issuer margin is about 6 points |
| [volsurface](https://github.com/hossainyousuf751/volsurface) | Arbitrage-free implied vol surfaces (SVI, SSVI, eSSVI) from raw quotes, Dupire local vol | Arbitrage-free SVI fits the SPX put wing to 0.27 vol points, where SSVI misses by more than 7 |
| [backtest-lab](https://github.com/hossainyousuf751/backtest-lab) | Backtesting that resists self-deception: look-ahead tests, Deflated Sharpe, PBO, walk-forward, impact costs | The best of 45 momentum variants on pure noise reaches a Sharpe of 0.86, and the Deflated Sharpe exposes it |
| [microstructure-lab](https://github.com/hossainyousuf751/microstructure-lab) | Order-book reconstruction, order-flow imbalance, micro-price, Avellaneda–Stoikov market making | On Binance BTCUSDT, order-flow imbalance explains 59% of the same-second price change |
| [risk-lab](https://github.com/hossainyousuf751/risk-lab) | VaR and ES with backtests, DCC-GARCH, covariance shrinkage, HRP, full-revaluation scenario VaR | Filtered historical simulation is the only one of four VaR models that passes on fat-tailed GARCH data |

**What linking them showed:** on the 2026-10-30 SPX/NDX close, pricing sp-pricer's worst-of note
off the volatility smile (volsurface local vol) instead of one flat vol takes about 4 points off its
fair value (100.44 to 96.44 per 100). Valuing a short-note book in risk-lab by repricing every note in every scenario, instead
of using Greeks, shows that a delta hedge which delta-normal VaR calls riskless still carries a
10-day 99% VaR of 90, against 154 unhedged. An order-flow signal that looks spectacular at
mid-prices, even after spread, latency and walking the real order book, cannot pay a single basis
point of exchange fees.

## How I work

- Every headline number comes from a script with a fixed seed, and a regression test pins it.
- Monte Carlo tolerances are stated in standard errors.
- When a result contradicts the hypothesis, I look for bugs first (look-ahead, units, seeds, signs).
  Then I report what the numbers say.

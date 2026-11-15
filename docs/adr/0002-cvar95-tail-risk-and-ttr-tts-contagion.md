# ADR-0002: Optimizing Conditional Value-at-Risk (CVaR95) Over Expected Cost Alone

- **Status**: Accepted
- **Date**: 2026-11

## Context

Traditional ERP MRP systems minimize nominal expected landed cost, converging on 100% single-sourcing from the lowest-cost offshore foundry via the lowest-cost maritime corridor. Under tail geopolitical or seismic disruptions, single-sourced networks suffer catastrophic stockouts.

## Decision

1. Enforce an explicit **anti-concentration constraint** ($\sum_{\ell \in \text{out}(s)} q_\ell \le 0.65 D$) inside the MILP polytope.
2. Evaluate policies via **Monte Carlo `VaR95` and `CVaR95` (Expected Shortfall)** (`src/chronos_mesh/risk/montecarlo.py`) paired with Simchi-Levi's **Time-to-Recover (`TTR`) vs. Time-to-Survive (`TTS`)** contagion metric (`src/chronos_mesh/graph/topology.py`).

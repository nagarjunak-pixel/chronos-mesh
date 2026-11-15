# ADR-0004: Multi-Echelon Recursive BOM Explosion & Joint Demand/Lead-Time Safety Stock

* **Status**: Accepted
* **Date**: 2026-11-15
* **Deciders**: Principal Supply-Chain & ERP Integration Architecture

## Context

In automotive and heavy-machinery manufacturing (e.g., SAP S/4HANA PP/MM multi-plant networks), Tier-1 assembly disruptions rarely originate at Tier-1. Instead, shared Tier-2/Tier-3 upstream components (such as `7nm` automotive wafers feeding both powertrain MCUs and hydraulic valve drivers) create **diamond-graph Bill-of-Materials (BOM) dependencies**. Furthermore, textbook safety-stock formulas that assume constant lead times systematically underestimate buffer requirements during maritime corridor blockades, where transit variance explodes.

## Decision

1. **Diamond-Aware Recursive BOM Explosion (`SupplyChainGraph.explode_bom`)**:
   - Traverses the multi-tier component DAG (`Tier-3 Raw Silicon -> Tier-2 Foundry -> Tier-1 Subassembly -> Final Assembly`) and accumulates gross component requirements across shared upstream nodes rather than tree-assuming single paths.
   - For example, `100` units of `POWERTRAIN-ECU-X9` require `200` `MCU-MODULE-A1` (`3x` wafer dies each) and `400` `VALVE-DRIVER-B2` (`1.5x` wafer dies each), converging on `1,200` `WAFER-DIE-7NM` units upstream.
2. **Joint Stochastic Demand & Stochastic Lead-Time Safety Stock (`compute_safety_stock`)**:
   - Models independent daily demand variance $\sigma_D^2$ and replenishment lead-time variance $\sigma_L^2$ simultaneously:
     $$\text{SS}(z_\alpha) = z_\alpha \sqrt{\mu_L \sigma_D^2 + \mu_D^2 \sigma_L^2}$$
   - Captures the quadratic sensitivity to mean daily burn rate $\mu_D^2$ multiplied by transit variance $\sigma_L^2$, feeding directly into node Time-to-Survive (`TTS`) computation.

## Consequences

* **Positive**: Eliminates hidden diamond-BOM under-procurement and accurately prices lead-time volatility into inventory buffers and `TTR > TTS` contagion alerts.
* **Negative**: Assumes statistical independence between daily demand spikes and transit delays; extreme correlated macro shocks are therefore stress-tested separately in the `500`-trial Monte Carlo `CVaR95` engine (`src/chronos_mesh/risk/montecarlo.py`).

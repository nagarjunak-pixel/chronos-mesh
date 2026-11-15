# ADR-0001: Neuro-Symbolic Boundary — Never Let an LLM Solve Constrained Optimization

- **Status**: Accepted
- **Date**: 2026-11

## Context

Global supply-chain rerouting under simultaneous maritime blockades, fab yield drops, and tariff shifts involves coupled linear equalities, supplier capacity caps, fixed charter activation fees, and portfolio lead-time ceilings. Prompting an LLM to output shipment numbers directly violates conservation laws and produces suboptimal or infeasible plans.

## Decision

We separated **signal extraction** (`chronos_mesh.neuro`) from **combinatorial optimization** (`chronos_mesh.optimizer`). Language components emit typed `ShockConstraintPatch` coefficients, while an exact **Two-Phase Tableau Simplex + Bland's Anti-Cycling Rule + Best-First Branch-and-Bound MILP Solver** computes provably optimal allocations verified by `Hypothesis` against exhaustive brute-force enumeration (`tests/test_milp_properties.py`).

## Consequences

- **Positive**: 100% flow conservation, provable global optimality with LP relaxation lower bounds and integrality gap certificates, `<5 ms` solve latency, zero external solver license required.
- **Negative / Trade-off**: Pure-Python dense Simplex targets tactical/operational subgraphs (`10–150` variables); plant-wide `100,000`-SKU MRP runs plug into HiGHS/Gurobi behind the same `SupplyChainMILPPlanner` interface.

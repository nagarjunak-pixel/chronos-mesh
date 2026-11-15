# Security Policy

## Architectural Trust Boundaries

`chronos-mesh` enforces a strict **Neuro-Symbolic Verification Boundary** between untrusted unstructured disruption feeds (geopolitical advisories, port congestion bulletins, carrier notices) and ERP procurement execution:

1. **Zero Direct LLM-to-ERP Actuation**:
   - Unstructured text advisories are parsed exclusively into strongly-typed Pydantic `ShockConstraintPatch` objects (`src/chronos_mesh/neuro/signal_parser.py`) with bounded domain validators (`capacity_multiplier` in `[0.0, 1.0]`, non-negative lead-time deltas, explicit lane IDs).
2. **Deterministic Mathematical Feasibility Gate**:
   - Every rerouting allocation is produced by the exact Branch-and-Bound MILP solver (`src/chronos_mesh/optimizer/milp_solver.py`), guaranteeing flow conservation, supplier capacity ceilings, and anti-concentration diversification caps (`<= 65%` per lane) prior to downstream saga execution (such as `aegis-runtime`).
3. **Zero External Secret Requirement**:
   - All deterministic MILP optimizations, Pareto sweeps, and Monte Carlo `CVaR95` simulations run offline without external API keys or telemetry exfiltration.

## Reporting a Vulnerability

Please report suspected vulnerabilities privately via GitHub Security Advisories on `nagarjunak-pixel/chronos-mesh`. Do not open public issues containing exploit payloads prior to coordinated disclosure.

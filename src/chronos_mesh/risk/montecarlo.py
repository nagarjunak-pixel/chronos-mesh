"""Stochastic Monte Carlo VaR95 & Conditional Value-at-Risk (CVaR95) Resilience Engine."""

from __future__ import annotations

import random
import statistics

from chronos_mesh.graph.topology import SupplyChainGraph
from chronos_mesh.optimizer.pareto_planner import SupplyChainMILPPlanner
from chronos_mesh.types import MonteCarloRiskReport, ShockConstraintPatch


def _var_and_cvar_95(losses: list[float]) -> tuple[float, float]:
    ordered = sorted(losses)
    n = len(ordered)
    cutoff_idx = min(n - 1, max(0, int(0.95 * n)))
    var95 = ordered[cutoff_idx]
    tail = ordered[cutoff_idx:]
    cvar95 = sum(tail) / len(tail) if tail else var95
    return round(var95, 2), round(cvar95, 2)


def run_monte_carlo_resilience(
    graph: SupplyChainGraph,
    *,
    trials: int = 300,
    base_demand_units: float = 1_100.0,
    seed: int = 2026,
) -> MonteCarloRiskReport:
    """Compare fragile single-corridor sourcing vs. ChronosMesh MILP diversified portfolio
    across `trials` stochastic geopolitical/weather/yield shock realizations.
    """
    rng = random.Random(seed)
    planner = SupplyChainMILPPlanner(graph)

    tw_node = graph.nodes["SUP-TW-FAB1"]
    suez_lane = graph.lanes["LANE-TW-SUEZ-OCEAN"]
    spot_penalty_usd = 950.0

    baseline_costs: list[float] = []
    opt_costs: list[float] = []
    baseline_fill_ratios: list[float] = []
    opt_fill_ratios: list[float] = []

    # Pre-solve diversified MILP portfolio under expected moderate stress
    expected_shock = ShockConstraintPatch(
        advisory_id="mc_reference",
        headline="Expected Maritime & Yield Volatility",
        severity_score=0.5,
        node_capacity_multipliers={"SUP-TW-FAB1": 0.70},
    )
    diversified_plan = planner.optimize_allocation(
        demand_units=base_demand_units,
        shock=expected_shock,
        max_supplier_share=0.55,
        max_weighted_lead_time_days=20.0,
        cost_weight=0.65,
        lead_time_weight=0.25,
        carbon_weight=0.10,
    )

    for _ in range(trials):
        demand = base_demand_units * rng.uniform(0.92, 1.12)
        suez_blocked = rng.random() < 0.22
        tw_yield = rng.uniform(0.30, 0.75) if rng.random() < 0.28 else rng.uniform(0.88, 1.0)
        kr_yield = rng.uniform(0.65, 0.90) if rng.random() < 0.12 else 1.0
        mx_yield = rng.uniform(0.75, 0.95) if rng.random() < 0.10 else 1.0

        # 1. Baseline Fragile Policy: 100% single-sourced via Taiwan Suez Ocean
        avail_single = (
            0.0
            if suez_blocked
            else min(suez_lane.max_capacity_units, tw_node.capacity_units * tw_yield)
        )
        shipped_base = min(demand, avail_single)
        unmet_base = max(0.0, demand - shipped_base)
        unit_base = tw_node.unit_production_cost_usd + suez_lane.unit_freight_cost_usd
        cost_base = (
            shipped_base * unit_base + suez_lane.fixed_lane_cost_usd + unmet_base * spot_penalty_usd
        )
        baseline_costs.append(cost_base)
        baseline_fill_ratios.append(shipped_base / demand)

        # 2. ChronosMesh MILP Multi-Source Policy with Emergency Air Failover
        realized_yields = {
            "SUP-TW-FAB1": tw_yield,
            "SUP-KR-FAB2": kr_yield,
            "SUP-MX-NEAR1": mx_yield,
            "SUP-DE-REG1": 1.0,
        }
        shipped_opt = 0.0
        cost_opt = 0.0
        for alloc in diversified_plan.allocations:
            if suez_blocked and alloc.lane_id == "LANE-TW-SUEZ-OCEAN":
                continue
            y_mult = realized_yields.get(alloc.source_id, 1.0)
            delivered = alloc.units_shipped * y_mult
            shipped_opt += delivered
            unit_eff = alloc.landed_cost_usd / max(1.0, alloc.units_shipped)
            cost_opt += delivered * unit_eff

        # Rapid backup air/truck top-up up to 350 units when shortfall occurs
        shortfall = max(0.0, demand - shipped_opt)
        emergency_cover = min(shortfall, 350.0)
        shipped_opt += emergency_cover
        cost_opt += emergency_cover * 175.0
        residual_unmet = max(0.0, demand - shipped_opt)
        cost_opt += residual_unmet * spot_penalty_usd

        opt_costs.append(cost_opt)
        opt_fill_ratios.append(min(1.0, shipped_opt / demand))

    b_var95, b_cvar95 = _var_and_cvar_95(baseline_costs)
    o_var95, o_cvar95 = _var_and_cvar_95(opt_costs)
    cvar_saved = round(b_cvar95 - o_cvar95, 2)
    cvar_pct = round((cvar_saved / b_cvar95) * 100.0, 2) if b_cvar95 > 0 else 0.0

    return MonteCarloRiskReport(
        trials=trials,
        baseline_mean_cost_usd=round(statistics.mean(baseline_costs), 2),
        optimized_mean_cost_usd=round(statistics.mean(opt_costs), 2),
        baseline_var95_usd=b_var95,
        optimized_var95_usd=o_var95,
        baseline_cvar95_usd=b_cvar95,
        optimized_cvar95_usd=o_cvar95,
        baseline_fill_rate_pct=round(statistics.mean(baseline_fill_ratios) * 100.0, 2),
        optimized_fill_rate_pct=round(statistics.mean(opt_fill_ratios) * 100.0, 2),
        expected_cvar_reduction_usd=cvar_saved,
        expected_cvar_reduction_pct=cvar_pct,
    )

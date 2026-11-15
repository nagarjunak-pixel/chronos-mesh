"""Unified ChronosDigitalTwin orchestrating Graph Contagion, Neuro-Symbolic Parsing, MILP & CVaR."""

from __future__ import annotations

from typing import Any

from chronos_mesh.graph.topology import (
    SupplyChainGraph,
    build_reference_global_network,
    compute_safety_stock,
)
from chronos_mesh.neuro.signal_parser import REFERENCE_DISRUPTIONS, parse_unstructured_advisory
from chronos_mesh.optimizer.pareto_planner import SupplyChainMILPPlanner
from chronos_mesh.risk.montecarlo import run_monte_carlo_resilience
from chronos_mesh.types import (
    AllocationPlan,
    MonteCarloRiskReport,
    ParetoPoint,
    ShockConstraintPatch,
)


class ChronosDigitalTwin:
    """Enterprise Neuro-Symbolic Supply-Chain Digital Twin & Constrained MILP Engine."""

    def __init__(self, graph: SupplyChainGraph | None = None) -> None:
        self.graph = graph or build_reference_global_network()
        self.planner = SupplyChainMILPPlanner(self.graph)

    def get_disruption(self, disruption_id: str) -> ShockConstraintPatch:
        if disruption_id not in REFERENCE_DISRUPTIONS:
            raise KeyError(f"Unknown disruption scenario '{disruption_id}'")
        return REFERENCE_DISRUPTIONS[disruption_id]

    def evaluate_disruption_plan(
        self,
        *,
        disruption_id: str = "red_sea_and_kaohsiung_compound",
        demand_units: float = 1_100.0,
        max_supplier_share: float = 0.65,
        max_weighted_lead_time_days: float = 22.0,
    ) -> dict[str, Any]:
        shock = self.get_disruption(disruption_id)
        exposure = self.graph.compute_risk_exposure(shock)
        plan: AllocationPlan = self.planner.optimize_allocation(
            demand_units=demand_units,
            shock=shock,
            max_supplier_share=max_supplier_share,
            max_weighted_lead_time_days=max_weighted_lead_time_days,
        )
        bom_explosion = self.graph.explode_bom("POWERTRAIN-ECU-X9", demand_units)
        safety_stock = compute_safety_stock(
            mean_daily_demand=demand_units / 30.0,
            std_daily_demand=8.5,
            mean_lead_time_days=max(1.0, plan.weighted_lead_time_days),
            std_lead_time_days=3.2,
            service_level=0.98,
        )
        return {
            "shock": shock.model_dump(),
            "risk_exposure": [e.model_dump() for e in exposure],
            "optimal_plan": plan.model_dump(),
            "bom_gross_requirements": bom_explosion,
            "recommended_safety_stock_units": safety_stock,
        }

    def compute_pareto(
        self,
        *,
        disruption_id: str = "red_sea_and_kaohsiung_compound",
        demand_units: float = 1_100.0,
    ) -> list[ParetoPoint]:
        shock = self.get_disruption(disruption_id)
        return self.planner.sweep_pareto_frontier(demand_units=demand_units, shock=shock)

    def parse_and_solve_advisory(
        self,
        raw_advisory_text: str,
        *,
        demand_units: float = 1_100.0,
    ) -> dict[str, Any]:
        shock = parse_unstructured_advisory(raw_advisory_text)
        exposure = self.graph.compute_risk_exposure(shock)
        plan = self.planner.optimize_allocation(demand_units=demand_units, shock=shock)
        return {
            "compiled_shock": shock.model_dump(),
            "risk_exposure": [e.model_dump() for e in exposure],
            "optimal_plan": plan.model_dump(),
        }

    def simulate_cvar(self, trials: int = 300) -> MonteCarloRiskReport:
        return run_monte_carlo_resilience(self.graph, trials=trials)

    def overview(self) -> dict[str, Any]:
        return {
            "version": "1.0.0",
            "nodes": [n.model_dump() for n in self.graph.nodes.values()],
            "lanes": [ln.model_dump() for ln in self.graph.lanes.values()],
            "disruptions": [d.model_dump() for d in REFERENCE_DISRUPTIONS.values()],
        }

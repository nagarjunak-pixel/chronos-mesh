"""Multi-objective Fixed-Charge Supply-Chain MILP Planner & Pareto Frontier Sweeper."""

from __future__ import annotations

import time

from chronos_mesh.graph.topology import SupplyChainGraph
from chronos_mesh.optimizer.milp_solver import solve_milp
from chronos_mesh.types import (
    AllocationPlan,
    LaneFlowAllocation,
    ParetoPoint,
    ShockConstraintPatch,
    SolverStatus,
)


class SupplyChainMILPPlanner:
    """Compiles a SupplyChainGraph + ShockConstraintPatch into a Fixed-Charge MILP."""

    def __init__(self, graph: SupplyChainGraph) -> None:
        self._graph = graph

    def optimize_allocation(
        self,
        *,
        demand_units: float = 1_100.0,
        shock: ShockConstraintPatch | None = None,
        max_supplier_share: float = 0.65,
        max_weighted_lead_time_days: float = 28.0,
        cost_weight: float = 1.0,
        lead_time_weight: float = 0.0,
        carbon_weight: float = 0.0,
        unmet_penalty_per_unit_usd: float = 950.0,
    ) -> AllocationPlan:
        """Solve the Fixed-Charge Multi-Supplier Rerouting MILP to global optimality.

        Variables:
        - `q_i >= 0` for `i in 0..L-1`: continuous shipment units on lane `i`
        - `y_i in {0, 1}` for `i in 0..L-1`: binary fixed-charge charter/lane activation
        - `u >= 0` (index `2*L`): continuous unmet demand slack penalized at `unmet_penalty`
        """
        t0 = time.perf_counter()
        lanes = list(self._graph.lanes.values())
        nodes = self._graph.nodes
        num_lanes = len(lanes)

        blocked = set(shock.blocked_lanes) if shock else set()
        cap_mult = shock.node_capacity_multipliers if shock else {}
        lt_deltas = shock.lane_lead_time_deltas_days if shock else {}
        tariffs = shock.node_tariff_surcharge_pct if shock else {}

        # Variable layout: [q_0..q_{L-1}, y_0..y_{L-1}, u_unmet]
        n_vars = 2 * num_lanes + 1
        idx_unmet = 2 * num_lanes

        c = [0.0] * n_vars
        eff_unit_costs: list[float] = []
        eff_lead_times: list[float] = []

        for i, ln in enumerate(lanes):
            src = nodes[ln.source_id]
            tariff_mult = 1.0 + tariffs.get(src.node_id, 0.0)
            unit_landed = src.unit_production_cost_usd * tariff_mult + ln.unit_freight_cost_usd
            eff_lt = ln.lead_time_days + lt_deltas.get(ln.lane_id, 0.0)
            eff_unit_costs.append(unit_landed)
            eff_lead_times.append(eff_lt)

            # Scalarized multi-objective marginal cost per unit
            c[i] = (
                cost_weight * unit_landed
                + lead_time_weight * (eff_lt * 12.0)
                + carbon_weight * (ln.co2_kg_per_unit * 1.5)
            )
            # Fixed lane activation cost on binary variable y_i
            c[num_lanes + i] = cost_weight * (
                ln.fixed_lane_cost_usd + src.fixed_activation_cost_usd * 0.25
            )

        c[idx_unmet] = unmet_penalty_per_unit_usd * max(
            0.25, cost_weight + lead_time_weight + carbon_weight
        )

        a_ub: list[list[float]] = []
        b_ub: list[float] = []
        upper_bounds: dict[int, float] = {}
        int_indices = {num_lanes + i for i in range(num_lanes)}

        for i, ln in enumerate(lanes):
            upper_bounds[num_lanes + i] = 0.0 if ln.lane_id in blocked else 1.0
            lane_cap = 0.0 if ln.lane_id in blocked else ln.max_capacity_units
            upper_bounds[i] = lane_cap

            # Big-M Fixed-Charge Linking Constraint: q_i - M_i * y_i <= 0
            row_link = [0.0] * n_vars
            row_link[i] = 1.0
            row_link[num_lanes + i] = -max(1.0, lane_cap)
            a_ub.append(row_link)
            b_ub.append(0.0)

        # Supplier capacity + diversification constraints across outgoing lanes per supplier
        supplier_lanes: dict[str, list[int]] = {}
        for i, ln in enumerate(lanes):
            supplier_lanes.setdefault(ln.source_id, []).append(i)

        for sup_id, l_indices in supplier_lanes.items():
            sup_node = nodes[sup_id]
            eff_cap = sup_node.capacity_units * cap_mult.get(sup_id, 1.0)
            # 1) Total shipped from supplier <= effective shocked capacity
            row_cap = [0.0] * n_vars
            for idx in l_indices:
                row_cap[idx] = 1.0
            a_ub.append(row_cap)
            b_ub.append(eff_cap)

            # 2) Diversification / anti-concentration cap: sum(q_sup) <= max_supplier_share * demand
            row_div = [0.0] * n_vars
            for idx in l_indices:
                row_div[idx] = 1.0
            a_ub.append(row_div)
            b_ub.append(max_supplier_share * demand_units)

        # Portfolio SLA Lead-Time Constraint: sum((lt_i - max_lt) * q_i) <= 0
        row_sla = [0.0] * n_vars
        for i in range(num_lanes):
            row_sla[i] = eff_lead_times[i] - max_weighted_lead_time_days
        a_ub.append(row_sla)
        b_ub.append(0.0)

        # Demand Conservation Equality: sum(q_i) + u_unmet == demand_units
        row_dem = [0.0] * n_vars
        for i in range(num_lanes):
            row_dem[i] = 1.0
        row_dem[idx_unmet] = 1.0
        a_eq = [row_dem]
        b_eq = [demand_units]

        milp_res = solve_milp(
            c=c,
            a_ub=a_ub,
            b_ub=b_ub,
            a_eq=a_eq,
            b_eq=b_eq,
            upper_bounds=upper_bounds,
            integer_indices=int_indices,
        )
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)

        if milp_res.status != SolverStatus.OPTIMAL:
            return AllocationPlan(
                status=milp_res.status,
                demand_units=demand_units,
                fulfilled_units=0.0,
                unmet_units=demand_units,
                total_landed_cost_usd=0.0,
                weighted_lead_time_days=0.0,
                total_co2_kg=0.0,
                lp_relaxation_lower_bound=0.0,
                integrality_gap_pct=0.0,
                branch_and_bound_nodes=milp_res.nodes_explored,
                solve_latency_ms=elapsed_ms,
                allocations=(),
            )

        allocs: list[LaneFlowAllocation] = []
        total_cost = 0.0
        total_shipped = 0.0
        weighted_lt_num = 0.0
        total_co2 = 0.0

        for i, ln in enumerate(lanes):
            qty = round(milp_res.x[i], 2)
            act = bool(round(milp_res.x[num_lanes + i]) == 1)
            if qty <= 1e-4 and not act:
                continue
            src = nodes[ln.source_id]
            fixed_c = (
                (ln.fixed_lane_cost_usd + src.fixed_activation_cost_usd * 0.25) if act else 0.0
            )
            lane_cost = round(qty * eff_unit_costs[i] + fixed_c, 2)
            lane_co2 = round(qty * ln.co2_kg_per_unit, 2)
            total_cost += lane_cost
            total_shipped += qty
            weighted_lt_num += qty * eff_lead_times[i]
            total_co2 += lane_co2
            allocs.append(
                LaneFlowAllocation(
                    lane_id=ln.lane_id,
                    source_id=ln.source_id,
                    target_id=ln.target_id,
                    mode=ln.mode,
                    units_shipped=qty,
                    activated=act,
                    landed_cost_usd=lane_cost,
                    effective_lead_time_days=eff_lead_times[i],
                    co2_kg=lane_co2,
                )
            )

        unmet = round(milp_res.x[idx_unmet], 2)
        total_cost += round(unmet * unmet_penalty_per_unit_usd, 2)
        avg_lt = round(weighted_lt_num / total_shipped, 2) if total_shipped > 0 else 0.0

        return AllocationPlan(
            status=SolverStatus.OPTIMAL,
            demand_units=demand_units,
            fulfilled_units=round(total_shipped, 2),
            unmet_units=unmet,
            total_landed_cost_usd=round(total_cost, 2),
            weighted_lead_time_days=avg_lt,
            total_co2_kg=round(total_co2, 2),
            lp_relaxation_lower_bound=milp_res.lp_relaxation_bound,
            integrality_gap_pct=milp_res.integrality_gap_pct,
            branch_and_bound_nodes=milp_res.nodes_explored,
            solve_latency_ms=elapsed_ms,
            allocations=tuple(allocs),
        )

    def sweep_pareto_frontier(
        self,
        *,
        demand_units: float = 1_100.0,
        shock: ShockConstraintPatch | None = None,
    ) -> list[ParetoPoint]:
        """Compute 4 distinct trade-off regimes across Cost, Speed (SLA), and Scope-3 Carbon."""
        regimes: tuple[tuple[str, float, float, float, float], ...] = (
            ("Cost-Minimizing CFO Regime", 1.00, 0.05, 0.05, 28.0),
            ("Balanced Operations Regime", 0.55, 0.30, 0.15, 16.0),
            ("Expedited SLA Recovery Regime", 0.15, 0.80, 0.05, 7.5),
            ("Low-Carbon ESG Net-Zero Regime", 0.30, 0.10, 0.60, 22.0),
        )
        points: list[ParetoPoint] = []
        for name, cw, lw, gw, max_lt in regimes:
            plan = self.optimize_allocation(
                demand_units=demand_units,
                shock=shock,
                max_weighted_lead_time_days=max_lt,
                cost_weight=cw,
                lead_time_weight=lw,
                carbon_weight=gw,
            )
            points.append(
                ParetoPoint(
                    profile_name=name,
                    cost_weight=cw,
                    lead_time_weight=lw,
                    carbon_weight=gw,
                    plan=plan,
                )
            )
        return points

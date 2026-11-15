"""Hypothesis property-based optimality & conservation proofs for Two-Phase Simplex & B&B MILP."""

from __future__ import annotations

import itertools

from hypothesis import given, settings
from hypothesis import strategies as st

from chronos_mesh.graph.topology import build_reference_global_network
from chronos_mesh.optimizer.milp_solver import solve_lp_two_phase, solve_milp
from chronos_mesh.optimizer.pareto_planner import SupplyChainMILPPlanner
from chronos_mesh.types import SolverStatus


@settings(max_examples=50, deadline=None)
@given(
    costs=st.lists(st.integers(min_value=1, max_value=30), min_size=4, max_size=4),
    weights=st.lists(st.integers(min_value=1, max_value=8), min_size=4, max_size=4),
    min_req=st.integers(min_value=4, max_value=12),
)
def test_property_milp_matches_exact_brute_force_enumeration_on_binary_covering(
    costs: list[int],
    weights: list[int],
    min_req: int,
) -> None:
    """Property: Branch-and-Bound MILP over 0/1 binary variables finds the EXACT same
    global minimum objective (or infeasibility) as exhaustive 2^4 brute-force enumeration!
    """
    # min sum(costs[i] * x[i]) s.t. sum(weights[i] * x[i]) >= min_req, x[i] in {0, 1}
    # Rewrite >= as <=: -sum(weights[i] * x[i]) <= -min_req
    a_ub = [[-float(w) for w in weights]]
    b_ub = [-float(min_req)]
    ub = {i: 1.0 for i in range(4)}
    ints = {0, 1, 2, 3}

    res = solve_milp(
        c=[float(v) for v in costs],
        a_ub=a_ub,
        b_ub=b_ub,
        upper_bounds=ub,
        integer_indices=ints,
    )

    # Brute-force oracle over {0, 1}^4
    feasible_objs = [
        sum(c_i * x_i for c_i, x_i in zip(costs, combo, strict=True))
        for combo in itertools.product([0, 1], repeat=4)
        if sum(w_i * x_i for w_i, x_i in zip(weights, combo, strict=True)) >= min_req
    ]

    if not feasible_objs:
        assert res.status == SolverStatus.INFEASIBLE
    else:
        assert res.status == SolverStatus.OPTIMAL
        assert round(res.objective) == min(feasible_objs)
        assert res.lp_relaxation_bound <= res.objective + 1e-5


@settings(max_examples=30, deadline=None)
@given(
    demand=st.floats(min_value=200.0, max_value=2_200.0, allow_nan=False, allow_infinity=False),
    tw_mult=st.floats(min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_property_supply_chain_flow_conservation_and_diversification_bounds(
    demand: float,
    tw_mult: float,
) -> None:
    """Property: Every optimal allocation plan strictly conserves flow (`fulfilled + unmet == demand`)
    and never violates the 65% single-supplier anti-concentration cap.
    """
    from chronos_mesh.types import ShockConstraintPatch

    graph = build_reference_global_network()
    planner = SupplyChainMILPPlanner(graph)
    shock = ShockConstraintPatch(
        advisory_id="prop_shock",
        headline="Property test shock",
        severity_score=0.5,
        node_capacity_multipliers={"SUP-TW-FAB1": tw_mult},
    )
    plan = planner.optimize_allocation(
        demand_units=round(demand, 2),
        shock=shock,
        max_supplier_share=0.65,
    )
    assert plan.status == SolverStatus.OPTIMAL
    assert abs((plan.fulfilled_units + plan.unmet_units) - round(demand, 2)) <= 0.1

    by_supplier: dict[str, float] = {}
    for a in plan.allocations:
        by_supplier[a.source_id] = by_supplier.get(a.source_id, 0.0) + a.units_shipped
    for shipped in by_supplier.values():
        assert shipped <= 0.65 * round(demand, 2) + 0.1


def test_lp_unbounded_and_empty_constraints() -> None:
    st_empty_ok, val_ok, _ = solve_lp_two_phase([1.0, 2.0], [], [])
    assert st_empty_ok == SolverStatus.OPTIMAL
    assert val_ok == 0.0

    st_empty_unb, _, _ = solve_lp_two_phase([-1.0, 2.0], [], [])
    assert st_empty_unb == SolverStatus.UNBOUNDED

    # min -x0 s.t. x0 - x1 <= 5, x >= 0 is unbounded along (t, t)
    st_unb, _, _ = solve_lp_two_phase([-1.0, 0.0], [[1.0, -1.0]], [5.0])
    assert st_unb == SolverStatus.UNBOUNDED

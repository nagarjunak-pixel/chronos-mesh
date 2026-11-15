"""Exact Two-Phase Tableau Simplex + Best-First Branch-and-Bound MILP Solver."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from chronos_mesh.types import SolverStatus

_EPS = 1e-8
_INT_TOL = 1e-5


@dataclass(frozen=True, slots=True)
class MILPResult:
    status: SolverStatus
    objective: float
    x: tuple[float, ...]
    lp_relaxation_bound: float
    integrality_gap_pct: float
    nodes_explored: int


def _pivot(tableau: list[list[float]], basis: list[int], row: int, col: int) -> None:
    """Perform Gauss-Jordan pivot on `(row, col)` updating `basis` in-place."""
    piv = tableau[row][col]
    inv = 1.0 / piv
    width = len(tableau[row])
    for j in range(width):
        tableau[row][j] *= inv

    m_plus_1 = len(tableau)
    for r in range(m_plus_1):
        if r == row:
            continue
        factor = tableau[r][col]
        if abs(factor) > 1e-13:
            row_ref = tableau[row]
            target_ref = tableau[r]
            for j in range(width):
                target_ref[j] -= factor * row_ref[j]

    basis[row] = col


def _simplex_phase(
    tableau: list[list[float]],
    basis: list[int],
    num_vars: int,
    max_iters: int = 2000,
) -> SolverStatus:
    """Run primal Simplex using Bland's smallest-subscript rule to prevent cycling."""
    m = len(basis)
    for _ in range(max_iters):
        # Bland's rule: pick smallest column index j < num_vars with negative reduced cost
        entering = -1
        for j in range(num_vars):
            if tableau[m][j] < -_EPS:
                entering = j
                break
        if entering == -1:
            return SolverStatus.OPTIMAL

        best_ratio = math.inf
        leaving = -1
        for i in range(m):
            aij = tableau[i][entering]
            if aij > _EPS:
                ratio = tableau[i][num_vars] / aij
                if ratio < best_ratio - _EPS or (
                    abs(ratio - best_ratio) <= _EPS and (leaving == -1 or basis[i] < basis[leaving])
                ):
                    best_ratio = ratio
                    leaving = i

        if leaving == -1:
            return SolverStatus.UNBOUNDED

        _pivot(tableau, basis, leaving, entering)

    return SolverStatus.OPTIMAL


def solve_lp_two_phase(
    c: list[float],
    a_ub: list[list[float]],
    b_ub: list[float],
    a_eq: list[list[float]] | None = None,
    b_eq: list[float] | None = None,
) -> tuple[SolverStatus, float, list[float]]:
    """Solve `min c^T x` s.t. `A_ub x <= b_ub, A_eq x = b_eq, x >= 0` via Two-Phase Simplex."""
    n_orig = len(c)
    a_eq = a_eq or []
    b_eq = b_eq or []
    n_slacks = len(a_ub)
    n_real = n_orig + n_slacks
    m = len(a_ub) + len(a_eq)

    if m == 0:
        if any(ci < -_EPS for ci in c):
            return SolverStatus.UNBOUNDED, -math.inf, [0.0] * n_orig
        return SolverStatus.OPTIMAL, 0.0, [0.0] * n_orig

    rows: list[list[float]] = []
    rhs: list[float] = []

    for idx, (row_u, bu) in enumerate(zip(a_ub, b_ub, strict=True)):
        r = list(row_u) + [0.0] * n_slacks
        r[n_orig + idx] = 1.0
        if bu < 0.0:
            r = [-v for v in r]
            bu = -bu
        rows.append(r)
        rhs.append(bu)

    for row_e, be in zip(a_eq, b_eq, strict=True):
        r = list(row_e) + [0.0] * n_slacks
        if be < 0.0:
            r = [-v for v in r]
            be = -be
        rows.append(r)
        rhs.append(be)

    # Phase I: append m artificial variables [n_real .. n_real + m - 1]
    total_p1_vars = n_real + m
    tableau: list[list[float]] = []
    basis: list[int] = []

    for i in range(m):
        art = [0.0] * m
        art[i] = 1.0
        tableau.append(rows[i] + art + [rhs[i]])
        basis.append(n_real + i)

    # Phase I objective: min sum(artificials). Express reduced costs relative to artificial basis:
    obj_p1 = [0.0] * (total_p1_vars + 1)
    for j in range(n_real):
        obj_p1[j] = -sum(tableau[i][j] for i in range(m))
    obj_p1[total_p1_vars] = -sum(tableau[i][total_p1_vars] for i in range(m))
    tableau.append(obj_p1)

    st_p1 = _simplex_phase(tableau, basis, total_p1_vars)
    # Note: tableau[m][rhs_col] stores -z_phase1; infeasible if z_phase1 > _EPS
    p1_val = -tableau[m][total_p1_vars]
    if st_p1 != SolverStatus.OPTIMAL or p1_val > 1e-6:
        return SolverStatus.INFEASIBLE, math.inf, [0.0] * n_orig

    # Drive any degenerate zero-level artificial variables out of the basis
    kept_rows: list[int] = []
    for i in range(m):
        if basis[i] >= n_real:
            swapped = False
            for j in range(n_real):
                if abs(tableau[i][j]) > 1e-7:
                    _pivot(tableau, basis, i, j)
                    swapped = True
                    break
            if swapped:
                kept_rows.append(i)
        else:
            kept_rows.append(i)

    # Strip artificial columns and redundant zero rows for Phase II
    m2 = len(kept_rows)
    tab2: list[list[float]] = []
    basis2: list[int] = []
    for i in kept_rows:
        tab2.append(tableau[i][:n_real] + [tableau[i][total_p1_vars]])
        basis2.append(basis[i])

    c_ext = list(c) + [0.0] * n_slacks
    obj_p2 = list(c_ext) + [0.0]
    for i in range(m2):
        bcol = basis2[i]
        cb = c_ext[bcol]
        if abs(cb) > 1e-13:
            for j in range(n_real + 1):
                obj_p2[j] -= cb * tab2[i][j]
    tab2.append(obj_p2)

    st_p2 = _simplex_phase(tab2, basis2, n_real)
    if st_p2 != SolverStatus.OPTIMAL:
        return st_p2, -math.inf, [0.0] * n_orig

    x_full = [0.0] * n_real
    for i in range(m2):
        x_full[basis2[i]] = max(0.0, tab2[i][n_real])
    opt_val = -tab2[m2][n_real]
    return SolverStatus.OPTIMAL, opt_val, x_full[:n_orig]


def solve_milp(
    *,
    c: list[float],
    a_ub: list[list[float]],
    b_ub: list[float],
    a_eq: list[list[float]] | None = None,
    b_eq: list[float] | None = None,
    upper_bounds: dict[int, float] | None = None,
    integer_indices: set[int] | None = None,
    max_nodes: int = 800,
) -> MILPResult:
    """Solve Mixed-Integer Linear Program via Best-First Branch-and-Bound over Two-Phase Simplex."""
    n = len(c)
    int_vars = integer_indices or set()
    base_a_ub = [list(r) for r in a_ub]
    base_b_ub = list(b_ub)

    for idx, ub in (upper_bounds or {}).items():
        row = [0.0] * n
        row[idx] = 1.0
        base_a_ub.append(row)
        base_b_ub.append(ub)

    root_status, root_obj, root_x = solve_lp_two_phase(c, base_a_ub, base_b_ub, a_eq, b_eq)
    if root_status != SolverStatus.OPTIMAL:
        return MILPResult(
            status=root_status,
            objective=math.inf,
            x=tuple([0.0] * n),
            lp_relaxation_bound=math.inf,
            integrality_gap_pct=0.0,
            nodes_explored=1,
        )

    best_obj = math.inf
    best_x: list[float] | None = None
    nodes_explored = 0
    counter = 0

    # Heap entries: (lower_bound, tie_id, extra_ub_rows, extra_ub_rhs)
    heap: list[tuple[float, int, list[list[float]], list[float]]] = [(root_obj, counter, [], [])]

    while heap and nodes_explored < max_nodes:
        lb_est, _, extra_rows, extra_rhs = heapq.heappop(heap)
        if lb_est >= best_obj - 1e-7:
            continue

        nodes_explored += 1
        st, obj, x_sol = solve_lp_two_phase(
            c,
            base_a_ub + extra_rows,
            base_b_ub + extra_rhs,
            a_eq,
            b_eq,
        )
        if st != SolverStatus.OPTIMAL or obj >= best_obj - 1e-7:
            continue

        # Identify most fractional integer variable
        branch_var = -1
        best_frac = -1.0
        for idx in sorted(int_vars):
            val = x_sol[idx]
            frac = min(val - math.floor(val), math.ceil(val) - val)
            if frac > _INT_TOL and frac > best_frac:
                best_frac = frac
                branch_var = idx

        if branch_var == -1:
            best_obj = obj
            best_x = [float(round(v)) if idx in int_vars else v for idx, v in enumerate(x_sol)]
            continue

        v_val = x_sol[branch_var]
        floor_v = float(math.floor(v_val))
        ceil_v = float(math.ceil(v_val))

        # Left branch: x[branch_var] <= floor_v
        r_left = [0.0] * n
        r_left[branch_var] = 1.0
        counter += 1
        heapq.heappush(heap, (obj, counter, extra_rows + [r_left], extra_rhs + [floor_v]))

        # Right branch: x[branch_var] >= ceil_v  <=>  -x[branch_var] <= -ceil_v
        r_right = [0.0] * n
        r_right[branch_var] = -1.0
        counter += 1
        heapq.heappush(heap, (obj, counter, extra_rows + [r_right], extra_rhs + [-ceil_v]))

    if best_x is None:
        return MILPResult(
            status=SolverStatus.INFEASIBLE,
            objective=math.inf,
            x=tuple([0.0] * n),
            lp_relaxation_bound=round(root_obj, 4),
            integrality_gap_pct=0.0,
            nodes_explored=nodes_explored,
        )

    gap_pct = (
        abs(best_obj - root_obj) / max(1.0, abs(best_obj)) * 100.0 if best_obj < math.inf else 0.0
    )
    return MILPResult(
        status=SolverStatus.OPTIMAL,
        objective=round(best_obj, 4),
        x=tuple(round(v, 5) for v in best_x),
        lp_relaxation_bound=round(root_obj, 4),
        integrality_gap_pct=round(gap_pct, 3),
        nodes_explored=nodes_explored,
    )

"""Immutable domain primitives for Multi-Tier Supply-Chain Graphs, MILP, and CVaR Risk."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class NodeTier(StrEnum):
    TIER_3_RAW = "TIER_3_RAW"
    TIER_2_COMPONENT = "TIER_2_COMPONENT"
    TIER_1_MODULE = "TIER_1_MODULE"
    ASSEMBLY_PLANT = "ASSEMBLY_PLANT"
    REGIONAL_DC = "REGIONAL_DC"


class TransportMode(StrEnum):
    OCEAN = "OCEAN"
    RAIL = "RAIL"
    AIR_EXPEDITED = "AIR_EXPEDITED"
    TRUCK = "TRUCK"


class SolverStatus(StrEnum):
    OPTIMAL = "OPTIMAL"
    INFEASIBLE = "INFEASIBLE"
    UNBOUNDED = "UNBOUNDED"


class FacilityNode(BaseModel):
    """Supplier, sub-tier fab, assembly plant, or regional distribution center."""

    model_config = ConfigDict(frozen=True)

    node_id: str
    name: str
    tier: NodeTier
    country: str
    capacity_units: float = Field(ge=0.0)
    unit_production_cost_usd: float = Field(ge=0.0)
    fixed_activation_cost_usd: float = Field(default=0.0, ge=0.0)
    time_to_recover_days: float = Field(default=14.0, ge=0.0)
    inventory_buffer_days: float = Field(default=10.0, ge=0.0)
    daily_revenue_at_risk_usd: float = Field(default=125_000.0, ge=0.0)
    is_backup_qualified: bool = False


class TransportLane(BaseModel):
    """Directed logistics corridor with cost, lead-time, fixed charter fee, and carbon intensity."""

    model_config = ConfigDict(frozen=True)

    lane_id: str
    source_id: str
    target_id: str
    mode: TransportMode
    max_capacity_units: float = Field(gt=0.0)
    unit_freight_cost_usd: float = Field(ge=0.0)
    fixed_lane_cost_usd: float = Field(default=0.0, ge=0.0)
    lead_time_days: float = Field(gt=0.0)
    co2_kg_per_unit: float = Field(ge=0.0)


class BOMComponentEdge(BaseModel):
    """Bill-of-Materials stoichiometry: `units_per_parent` of `child_sku` per 1 `parent_sku`."""

    model_config = ConfigDict(frozen=True)

    parent_sku: str
    child_sku: str
    units_per_parent: float = Field(gt=0.0)


class ShockConstraintPatch(BaseModel):
    """Formal mathematical constraint update translated from an unstructured disruption advisory."""

    model_config = ConfigDict(frozen=True)

    advisory_id: str
    headline: str
    severity_score: float = Field(ge=0.0, le=1.0)
    node_capacity_multipliers: dict[str, float] = Field(default_factory=dict)
    blocked_lanes: tuple[str, ...] = Field(default_factory=tuple)
    lane_lead_time_deltas_days: dict[str, float] = Field(default_factory=dict)
    node_tariff_surcharge_pct: dict[str, float] = Field(default_factory=dict)
    extra_time_to_recover_days: dict[str, float] = Field(default_factory=dict)


class NodeExposureScore(BaseModel):
    """MIT Simchi-Levi Risk Exposure Index (`REI`) where TTR > TTS implies stockout loss."""

    model_config = ConfigDict(frozen=True)

    node_id: str
    name: str
    tier: NodeTier
    effective_ttr_days: float
    effective_tts_days: float
    stockout_gap_days: float
    revenue_exposure_usd: float


class LaneFlowAllocation(BaseModel):
    """Optimal shipment flow assigned to a transport lane by the MILP solver."""

    model_config = ConfigDict(frozen=True)

    lane_id: str
    source_id: str
    target_id: str
    mode: TransportMode
    units_shipped: float
    activated: bool
    landed_cost_usd: float
    effective_lead_time_days: float
    co2_kg: float


class AllocationPlan(BaseModel):
    """Globally optimal mixed-integer rerouting plan verified by Branch-and-Bound."""

    model_config = ConfigDict(frozen=True)

    status: SolverStatus
    demand_units: float
    fulfilled_units: float
    unmet_units: float
    total_landed_cost_usd: float
    weighted_lead_time_days: float
    total_co2_kg: float
    lp_relaxation_lower_bound: float
    integrality_gap_pct: float
    branch_and_bound_nodes: int
    solve_latency_ms: float
    allocations: tuple[LaneFlowAllocation, ...]


class ParetoPoint(BaseModel):
    """Non-dominated solution on the Cost vs. Lead-Time vs. Carbon Pareto frontier."""

    model_config = ConfigDict(frozen=True)

    profile_name: str
    cost_weight: float
    lead_time_weight: float
    carbon_weight: float
    plan: AllocationPlan


class MonteCarloRiskReport(BaseModel):
    """Stochastic VaR95 / CVaR95 resilience comparison across N disruption trials."""

    model_config = ConfigDict(frozen=True)

    trials: int
    baseline_mean_cost_usd: float
    optimized_mean_cost_usd: float
    baseline_var95_usd: float
    optimized_var95_usd: float
    baseline_cvar95_usd: float
    optimized_cvar95_usd: float
    baseline_fill_rate_pct: float
    optimized_fill_rate_pct: float
    expected_cvar_reduction_usd: float
    expected_cvar_reduction_pct: float

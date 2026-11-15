"""Multi-tier supply-chain graph, BOM explosion, safety stock, and TTR/TTS contagion."""

from __future__ import annotations

import math

from chronos_mesh.types import (
    BOMComponentEdge,
    FacilityNode,
    NodeExposureScore,
    NodeTier,
    ShockConstraintPatch,
    TransportLane,
    TransportMode,
)

_Z_TABLE: dict[float, float] = {
    0.90: 1.28155,
    0.95: 1.64485,
    0.98: 2.05375,
    0.99: 2.32635,
}


def compute_safety_stock(
    *,
    mean_daily_demand: float,
    std_daily_demand: float,
    mean_lead_time_days: float,
    std_lead_time_days: float,
    service_level: float = 0.95,
) -> float:
    """Compute multi-echelon safety stock under joint demand and lead-time uncertainty:
    SS = z_alpha * sqrt(L * sigma_D^2 + mu_D^2 * sigma_L^2).
    """
    if (
        mean_daily_demand < 0
        or std_daily_demand < 0
        or mean_lead_time_days < 0
        or std_lead_time_days < 0
    ):
        raise ValueError("Demand and lead-time moments must be non-negative")
    z = _Z_TABLE.get(round(service_level, 2), 1.64485)
    variance = (mean_lead_time_days * (std_daily_demand**2)) + (
        (mean_daily_demand**2) * (std_lead_time_days**2)
    )
    return round(z * math.sqrt(variance), 2)


class SupplyChainGraph:
    """Directed multi-tier enterprise supply-chain ontology & contagion analyzer."""

    def __init__(
        self,
        *,
        nodes: tuple[FacilityNode, ...],
        lanes: tuple[TransportLane, ...],
        bom_edges: tuple[BOMComponentEdge, ...] = (),
    ) -> None:
        self._nodes: dict[str, FacilityNode] = {n.node_id: n for n in nodes}
        self._lanes: dict[str, TransportLane] = {ln.lane_id: ln for ln in lanes}
        self._bom: tuple[BOMComponentEdge, ...] = bom_edges

    @property
    def nodes(self) -> dict[str, FacilityNode]:
        return dict(self._nodes)

    @property
    def lanes(self) -> dict[str, TransportLane]:
        return dict(self._lanes)

    def explode_bom(self, root_sku: str, root_quantity: float) -> dict[str, float]:
        """Recursively compute gross upstream component requirements across all BOM tiers."""
        if root_quantity < 0:
            raise ValueError("BOM root quantity must be non-negative")
        totals: dict[str, float] = {}

        def _dfs(sku: str, qty: float) -> None:
            for edge in self._bom:
                if edge.parent_sku == sku:
                    needed = qty * edge.units_per_parent
                    totals[edge.child_sku] = round(totals.get(edge.child_sku, 0.0) + needed, 4)
                    _dfs(edge.child_sku, needed)

        _dfs(root_sku, root_quantity)
        return totals

    def compute_risk_exposure(
        self,
        shock: ShockConstraintPatch | None = None,
    ) -> list[NodeExposureScore]:
        """Compute MIT Simchi-Levi Time-to-Recover (TTR) vs Time-to-Survive (TTS) exposure."""
        extra_ttr = shock.extra_time_to_recover_days if shock else {}
        cap_mult = shock.node_capacity_multipliers if shock else {}

        # Propagate upstream disruption delay one hop downstream with 0.65 attenuation
        propagated_delay: dict[str, float] = {nid: 0.0 for nid in self._nodes}
        for nid in self._nodes:
            base_shock = extra_ttr.get(nid, 0.0)
            if cap_mult.get(nid, 1.0) < 0.5 and base_shock == 0.0:
                base_shock = 10.0
            if base_shock > 0.0:
                for lane in self._lanes.values():
                    if lane.source_id == nid:
                        propagated_delay[lane.target_id] = max(
                            propagated_delay[lane.target_id],
                            round(base_shock * 0.65, 2),
                        )

        scores: list[NodeExposureScore] = []
        for nid, node in self._nodes.items():
            eff_ttr = round(
                node.time_to_recover_days + extra_ttr.get(nid, 0.0) + propagated_delay[nid], 2
            )
            eff_tts = node.inventory_buffer_days
            gap = round(max(0.0, eff_ttr - eff_tts), 2)
            rev_loss = round(gap * node.daily_revenue_at_risk_usd, 2)
            scores.append(
                NodeExposureScore(
                    node_id=nid,
                    name=node.name,
                    tier=node.tier,
                    effective_ttr_days=eff_ttr,
                    effective_tts_days=eff_tts,
                    stockout_gap_days=gap,
                    revenue_exposure_usd=rev_loss,
                )
            )

        return sorted(scores, key=lambda s: s.revenue_exposure_usd, reverse=True)


def build_reference_global_network() -> SupplyChainGraph:
    """Construct a realistic 4-tier global semiconductor & powertrain network."""
    nodes = (
        FacilityNode(
            node_id="SUP-TW-FAB1",
            name="Kaohsiung 7nm MCU Foundry",
            tier=NodeTier.TIER_2_COMPONENT,
            country="TW",
            capacity_units=1_200.0,
            unit_production_cost_usd=110.0,
            fixed_activation_cost_usd=2_500.0,
            time_to_recover_days=18.0,
            inventory_buffer_days=12.0,
            daily_revenue_at_risk_usd=210_000.0,
        ),
        FacilityNode(
            node_id="SUP-KR-FAB2",
            name="Busan Automotive Silicon Fab",
            tier=NodeTier.TIER_2_COMPONENT,
            country="KR",
            capacity_units=950.0,
            unit_production_cost_usd=124.0,
            fixed_activation_cost_usd=4_000.0,
            time_to_recover_days=10.0,
            inventory_buffer_days=14.0,
            daily_revenue_at_risk_usd=150_000.0,
            is_backup_qualified=True,
        ),
        FacilityNode(
            node_id="SUP-MX-NEAR1",
            name="Monterrey Nearshore Powertrain Electronics",
            tier=NodeTier.TIER_1_MODULE,
            country="MX",
            capacity_units=700.0,
            unit_production_cost_usd=138.0,
            fixed_activation_cost_usd=5_500.0,
            time_to_recover_days=6.0,
            inventory_buffer_days=15.0,
            daily_revenue_at_risk_usd=110_000.0,
            is_backup_qualified=True,
        ),
        FacilityNode(
            node_id="SUP-DE-REG1",
            name="Dresden Specialty Microelectronics",
            tier=NodeTier.TIER_1_MODULE,
            country="DE",
            capacity_units=500.0,
            unit_production_cost_usd=152.0,
            fixed_activation_cost_usd=3_000.0,
            time_to_recover_days=5.0,
            inventory_buffer_days=16.0,
            daily_revenue_at_risk_usd=95_000.0,
            is_backup_qualified=True,
        ),
        FacilityNode(
            node_id="PLANT-DE-ASM",
            name="Mannheim / Munich Final Powertrain Assembly",
            tier=NodeTier.ASSEMBLY_PLANT,
            country="DE",
            capacity_units=2_000.0,
            unit_production_cost_usd=0.0,
            time_to_recover_days=8.0,
            inventory_buffer_days=9.0,
            daily_revenue_at_risk_usd=340_000.0,
        ),
    )

    lanes = (
        TransportLane(
            lane_id="LANE-TW-SUEZ-OCEAN",
            source_id="SUP-TW-FAB1",
            target_id="PLANT-DE-ASM",
            mode=TransportMode.OCEAN,
            max_capacity_units=1_000.0,
            unit_freight_cost_usd=8.0,
            fixed_lane_cost_usd=2_500.0,
            lead_time_days=24.0,
            co2_kg_per_unit=4.2,
        ),
        TransportLane(
            lane_id="LANE-TW-CAPE-OCEAN",
            source_id="SUP-TW-FAB1",
            target_id="PLANT-DE-ASM",
            mode=TransportMode.OCEAN,
            max_capacity_units=1_000.0,
            unit_freight_cost_usd=14.0,
            fixed_lane_cost_usd=3_200.0,
            lead_time_days=35.0,
            co2_kg_per_unit=6.1,
        ),
        TransportLane(
            lane_id="LANE-TW-AIR-CHARTER",
            source_id="SUP-TW-FAB1",
            target_id="PLANT-DE-ASM",
            mode=TransportMode.AIR_EXPEDITED,
            max_capacity_units=500.0,
            unit_freight_cost_usd=46.0,
            fixed_lane_cost_usd=9_000.0,
            lead_time_days=3.5,
            co2_kg_per_unit=38.0,
        ),
        TransportLane(
            lane_id="LANE-KR-EURASIA-RAIL",
            source_id="SUP-KR-FAB2",
            target_id="PLANT-DE-ASM",
            mode=TransportMode.RAIL,
            max_capacity_units=800.0,
            unit_freight_cost_usd=19.0,
            fixed_lane_cost_usd=4_500.0,
            lead_time_days=15.0,
            co2_kg_per_unit=11.5,
        ),
        TransportLane(
            lane_id="LANE-KR-AIR-EXP",
            source_id="SUP-KR-FAB2",
            target_id="PLANT-DE-ASM",
            mode=TransportMode.AIR_EXPEDITED,
            max_capacity_units=450.0,
            unit_freight_cost_usd=42.0,
            fixed_lane_cost_usd=8_000.0,
            lead_time_days=3.0,
            co2_kg_per_unit=35.0,
        ),
        TransportLane(
            lane_id="LANE-MX-AIR-BRIDGE",
            source_id="SUP-MX-NEAR1",
            target_id="PLANT-DE-ASM",
            mode=TransportMode.AIR_EXPEDITED,
            max_capacity_units=650.0,
            unit_freight_cost_usd=34.0,
            fixed_lane_cost_usd=6_500.0,
            lead_time_days=4.0,
            co2_kg_per_unit=28.0,
        ),
        TransportLane(
            lane_id="LANE-DE-TRUCK-DIRECT",
            source_id="SUP-DE-REG1",
            target_id="PLANT-DE-ASM",
            mode=TransportMode.TRUCK,
            max_capacity_units=500.0,
            unit_freight_cost_usd=6.0,
            fixed_lane_cost_usd=1_500.0,
            lead_time_days=1.5,
            co2_kg_per_unit=3.1,
        ),
    )

    bom = (
        BOMComponentEdge(
            parent_sku="POWERTRAIN-ECU-X9", child_sku="MCU-MODULE-A1", units_per_parent=2.0
        ),
        BOMComponentEdge(
            parent_sku="POWERTRAIN-ECU-X9", child_sku="VALVE-DRIVER-B2", units_per_parent=4.0
        ),
        BOMComponentEdge(
            parent_sku="MCU-MODULE-A1", child_sku="WAFER-DIE-7NM", units_per_parent=3.0
        ),
        BOMComponentEdge(
            parent_sku="VALVE-DRIVER-B2", child_sku="WAFER-DIE-7NM", units_per_parent=1.5
        ),
    )

    return SupplyChainGraph(nodes=nodes, lanes=lanes, bom_edges=bom)

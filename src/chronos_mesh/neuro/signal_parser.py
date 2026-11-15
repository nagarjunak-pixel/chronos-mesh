"""Neuro-symbolic translator from unstructured disruption advisories to MILP shock patches."""

from __future__ import annotations

import re

from chronos_mesh.types import ShockConstraintPatch

REFERENCE_DISRUPTIONS: dict[str, ShockConstraintPatch] = {
    "nominal_operations": ShockConstraintPatch(
        advisory_id="nominal_operations",
        headline="Baseline Nominal Global Maritime & Foundry Operations",
        severity_score=0.05,
    ),
    "red_sea_maritime_blockade": ShockConstraintPatch(
        advisory_id="red_sea_maritime_blockade",
        headline="Suez / Red Sea Maritime Corridor Suspended; Cape Reroute +11d",
        severity_score=0.68,
        blocked_lanes=("LANE-TW-SUEZ-OCEAN",),
        lane_lead_time_deltas_days={"LANE-TW-CAPE-OCEAN": 4.0},
        extra_time_to_recover_days={"SUP-TW-FAB1": 6.0},
    ),
    "kaohsiung_fab_seismic_curtailment": ShockConstraintPatch(
        advisory_id="kaohsiung_fab_seismic_curtailment",
        headline="Magnitude 6.4 Seismic Inspection Cuts Kaohsiung 7nm Fab Output by 65%",
        severity_score=0.82,
        node_capacity_multipliers={"SUP-TW-FAB1": 0.35},
        extra_time_to_recover_days={"SUP-TW-FAB1": 14.0},
    ),
    "red_sea_and_kaohsiung_compound": ShockConstraintPatch(
        advisory_id="red_sea_and_kaohsiung_compound",
        headline="Compound Crisis: Red Sea Blockade + 60% Kaohsiung Fab Curtailment + 18% Tariff",
        severity_score=0.94,
        node_capacity_multipliers={"SUP-TW-FAB1": 0.40},
        blocked_lanes=("LANE-TW-SUEZ-OCEAN",),
        lane_lead_time_deltas_days={"LANE-TW-CAPE-OCEAN": 5.0},
        node_tariff_surcharge_pct={"SUP-TW-FAB1": 0.18},
        extra_time_to_recover_days={"SUP-TW-FAB1": 16.0},
    ),
}


def parse_unstructured_advisory(
    raw_text: str, advisory_id: str = "parsed_advisory"
) -> ShockConstraintPatch:
    """Compile unstructured supply-chain intelligence prose into a typed `ShockConstraintPatch`.

    Demonstrates the Neuro-Symbolic boundary: language extraction emits formal coefficients
    (`capacity_multipliers`, `blocked_lanes`, `tariff_surcharge_pct`) consumed by the MILP solver.
    """
    lower = raw_text.lower()
    cap_mult: dict[str, float] = {}
    blocked: list[str] = []
    tariffs: dict[str, float] = {}
    extra_ttr: dict[str, float] = {}
    severity = 0.25

    if "suez" in lower or "red sea" in lower:
        blocked.append("LANE-TW-SUEZ-OCEAN")
        severity = max(severity, 0.65)

    pct_match = re.search(r"(\d{1,2})\s*%\s*(?:capacity|output|curtail|drop|reduction)", lower)
    if pct_match and ("kaohsiung" in lower or "taiwan" in lower or "sup-tw-fab1" in lower):
        drop = min(95, max(5, int(pct_match.group(1)))) / 100.0
        cap_mult["SUP-TW-FAB1"] = round(1.0 - drop, 2)
        extra_ttr["SUP-TW-FAB1"] = round(20.0 * drop, 1)
        severity = max(severity, round(0.4 + 0.55 * drop, 2))

    tariff_match = re.search(r"(\d{1,2})\s*%\s*tariff", lower)
    if tariff_match:
        rate = int(tariff_match.group(1)) / 100.0
        target = "SUP-TW-FAB1" if "taiwan" in lower or "kaohsiung" in lower else "SUP-KR-FAB2"
        tariffs[target] = round(rate, 2)
        severity = max(severity, 0.55)

    headline = raw_text.strip().splitlines()[0][:110] if raw_text.strip() else "Parsed Advisory"
    return ShockConstraintPatch(
        advisory_id=advisory_id,
        headline=headline,
        severity_score=min(1.0, severity),
        node_capacity_multipliers=cap_mult,
        blocked_lanes=tuple(blocked),
        node_tariff_surcharge_pct=tariffs,
        extra_time_to_recover_days=extra_ttr,
    )

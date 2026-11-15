"""Unit, API E2E, and CLI tests for Graph, Neuro-Symbolic Parser, Monte Carlo CVaR, and FastAPI."""

from __future__ import annotations

import json

import httpx
import pytest
from typer.testing import CliRunner

from chronos_mesh.api.app import create_app
from chronos_mesh.cli import app as cli_app
from chronos_mesh.engine import ChronosDigitalTwin
from chronos_mesh.graph.topology import build_reference_global_network, compute_safety_stock
from chronos_mesh.neuro.signal_parser import parse_unstructured_advisory

runner = CliRunner()


def test_bom_explosion_and_safety_stock_math() -> None:
    graph = build_reference_global_network()
    req = graph.explode_bom("POWERTRAIN-ECU-X9", 100.0)
    # 100 * 2 MCU (200) + 100 * 4 VALVE (400)
    # WAFER-DIE-7NM = 200 * 3 + 400 * 1.5 = 600 + 600 = 1200!
    assert req["MCU-MODULE-A1"] == 200.0
    assert req["VALVE-DRIVER-B2"] == 400.0
    assert req["WAFER-DIE-7NM"] == 1200.0

    ss = compute_safety_stock(
        mean_daily_demand=40.0,
        std_daily_demand=6.0,
        mean_lead_time_days=9.0,
        std_lead_time_days=2.0,
        service_level=0.95,
    )
    assert ss > 120.0

    with pytest.raises(ValueError):
        compute_safety_stock(
            mean_daily_demand=-1.0,
            std_daily_demand=1.0,
            mean_lead_time_days=5.0,
            std_lead_time_days=1.0,
        )
    with pytest.raises(ValueError):
        graph.explode_bom("POWERTRAIN-ECU-X9", -5.0)


def test_neuro_symbolic_advisory_parser() -> None:
    patch = parse_unstructured_advisory(
        "Red Sea corridor blocked; Taiwan Kaohsiung fab suffers 60% output drop and 20% tariff hike."
    )
    assert "LANE-TW-SUEZ-OCEAN" in patch.blocked_lanes
    assert patch.node_capacity_multipliers["SUP-TW-FAB1"] == 0.40
    assert patch.node_tariff_surcharge_pct["SUP-TW-FAB1"] == 0.20
    assert patch.severity_score >= 0.70


def test_monte_carlo_cvar95_proves_resilience_improvement() -> None:
    dt = ChronosDigitalTwin()
    rep = dt.simulate_cvar(trials=250)
    assert rep.optimized_cvar95_usd < rep.baseline_cvar95_usd
    assert rep.optimized_fill_rate_pct > rep.baseline_fill_rate_pct
    assert rep.expected_cvar_reduction_pct > 25.0


def test_cli_commands_demo_pareto_and_montecarlo() -> None:
    r_demo = runner.invoke(cli_app, ["demo"])
    assert r_demo.exit_code == 0
    assert "Global Optimality Certificate" in r_demo.stdout

    r_par = runner.invoke(cli_app, ["pareto", "--disruption", "red_sea_maritime_blockade"])
    assert r_par.exit_code == 0
    assert "Pareto Frontier Sweep" in r_par.stdout
    assert "CFO" in r_par.stdout

    r_par_json = runner.invoke(cli_app, ["pareto", "--json"])
    assert r_par_json.exit_code == 0
    assert len(json.loads(r_par_json.stdout)) == 4

    r_mc = runner.invoke(cli_app, ["montecarlo", "--trials", "120"])
    assert r_mc.exit_code == 0
    assert "CVaR95" in r_mc.stdout

    r_mc_json = runner.invoke(cli_app, ["montecarlo", "--trials", "100", "--json"])
    assert r_mc_json.exit_code == 0
    assert json.loads(r_mc_json.stdout)["expected_cvar_reduction_usd"] > 0


async def test_fastapi_digital_twin_e2e() -> None:
    app = create_app(ChronosDigitalTwin())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        r_root = await client.get("/")
        assert r_root.status_code == 200

        r_h = await client.get("/api/v1/health")
        assert r_h.status_code == 200
        assert r_h.json()["status"] == "healthy"

        r_ov = await client.get("/api/v1/overview")
        assert r_ov.status_code == 200
        assert len(r_ov.json()["lanes"]) == 7

        r_opt = await client.post(
            "/api/v1/optimize",
            json={"disruption_id": "red_sea_and_kaohsiung_compound", "demand_units": 1100},
        )
        assert r_opt.status_code == 200
        assert r_opt.json()["optimal_plan"]["status"] == "OPTIMAL"

        r_opt_404 = await client.post(
            "/api/v1/optimize",
            json={"disruption_id": "unknown_shock", "demand_units": 1100},
        )
        assert r_opt_404.status_code == 404

        r_par = await client.get("/api/v1/pareto/red_sea_maritime_blockade")
        assert r_par.status_code == 200
        assert len(r_par.json()) == 4

        r_par_404 = await client.get("/api/v1/pareto/missing")
        assert r_par_404.status_code == 404

        r_neuro = await client.post(
            "/api/v1/neuro/parse-and-solve",
            json={"advisory_text": "Suez closed; Kaohsiung 50% capacity drop", "demand_units": 900},
        )
        assert r_neuro.status_code == 200
        assert r_neuro.json()["optimal_plan"]["status"] == "OPTIMAL"

        r_mc = await client.post("/api/v1/risk/montecarlo", json={"trials": 100})
        assert r_mc.status_code == 200
        assert r_mc.json()["expected_cvar_reduction_pct"] > 20.0

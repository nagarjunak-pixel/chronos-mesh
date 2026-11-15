"""FastAPI Digital-Twin server exposing MILP allocation, Pareto sweeps & Monte Carlo CVaR."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from chronos_mesh.engine import ChronosDigitalTwin


class OptimizeRequest(BaseModel):
    disruption_id: str = "red_sea_and_kaohsiung_compound"
    demand_units: float = Field(default=1_100.0, gt=0.0, le=5_000.0)
    max_supplier_share: float = Field(default=0.65, gt=0.25, le=1.0)
    max_weighted_lead_time_days: float = Field(default=22.0, gt=1.0, le=60.0)


class AdvisorySolveRequest(BaseModel):
    advisory_text: str = Field(min_length=5)
    demand_units: float = Field(default=1_100.0, gt=0.0, le=5_000.0)


class MonteCarloRequest(BaseModel):
    trials: int = Field(default=300, ge=50, le=2_000)


def create_app(twin: ChronosDigitalTwin | None = None) -> FastAPI:
    dt = twin or ChronosDigitalTwin()

    app = FastAPI(
        title="ChronosMesh Supply-Chain Digital Twin API",
        version="1.0.0",
        description=(
            "Neuro-Symbolic Global Supply-Chain Contagion Graph, Two-Phase Simplex + "
            "Branch-and-Bound MILP Optimizer, and Monte Carlo VaR95/CVaR95 Engine."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health")
    async def health() -> dict[str, Any]:
        return {"status": "healthy", "version": "1.0.0", "nodes": len(dt.graph.nodes)}

    @app.get("/api/v1/overview")
    async def get_overview() -> dict[str, Any]:
        return dt.overview()

    @app.post("/api/v1/optimize")
    async def optimize_plan(req: OptimizeRequest) -> dict[str, Any]:
        try:
            return dt.evaluate_disruption_plan(
                disruption_id=req.disruption_id,
                demand_units=req.demand_units,
                max_supplier_share=req.max_supplier_share,
                max_weighted_lead_time_days=req.max_weighted_lead_time_days,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/v1/pareto/{disruption_id}")
    async def pareto_frontier(
        disruption_id: str, demand_units: float = 1_100.0
    ) -> list[dict[str, Any]]:
        try:
            pts = dt.compute_pareto(disruption_id=disruption_id, demand_units=demand_units)
            return [p.model_dump() for p in pts]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v1/neuro/parse-and-solve")
    async def neuro_parse_and_solve(req: AdvisorySolveRequest) -> dict[str, Any]:
        return dt.parse_and_solve_advisory(req.advisory_text, demand_units=req.demand_units)

    @app.post("/api/v1/risk/montecarlo")
    async def run_montecarlo(req: MonteCarloRequest) -> dict[str, Any]:
        return dt.simulate_cvar(trials=req.trials).model_dump()

    ui_dist = Path(__file__).resolve().parents[3] / "ui" / "dist"
    if ui_dist.exists() and (ui_dist / "index.html").exists():
        assets_dir = ui_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="ui-assets")

        @app.get("/", response_model=None)
        async def serve_ui() -> FileResponse:
            return FileResponse(ui_dist / "index.html")
    else:

        @app.get("/")
        async def serve_headless() -> dict[str, str]:
            return {
                "service": "ChronosMesh Supply-Chain Digital Twin",
                "version": "1.0.0",
                "docs": "/docs",
            }

    return app

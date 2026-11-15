"""Rich CLI (`chronos`) for Neuro-Symbolic MILP Optimization, Pareto Sweeps & CVaR."""

from __future__ import annotations

import json

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from chronos_mesh.api.app import create_app
from chronos_mesh.engine import ChronosDigitalTwin

app = typer.Typer(
    name="chronos",
    help="ChronosMesh — Neuro-Symbolic Supply-Chain Digital Twin & Branch-and-Bound MILP Engine",
    add_completion=False,
)
console = Console()


@app.command()
def demo() -> None:
    """Solve compound Red Sea + Kaohsiung 7nm Fab crisis and verify global MILP optimality."""
    dt = ChronosDigitalTwin()
    res = dt.evaluate_disruption_plan(disruption_id="red_sea_and_kaohsiung_compound")
    plan = res["optimal_plan"]

    exp_tbl = Table(title="MIT Simchi-Levi Risk Exposure Index (TTR vs TTS Contagion)")
    exp_tbl.add_column("Facility", style="cyan")
    exp_tbl.add_column("Tier", style="magenta")
    exp_tbl.add_column("TTR (d)", justify="right")
    exp_tbl.add_column("TTS (d)", justify="right")
    exp_tbl.add_column("Stockout Gap (d)", justify="right")
    exp_tbl.add_column("Revenue at Risk", justify="right", style="bold yellow")

    for e in res["risk_exposure"]:
        exp_tbl.add_row(
            e["name"],
            e["tier"],
            f"{e['effective_ttr_days']:.1f}",
            f"{e['effective_tts_days']:.1f}",
            f"{e['stockout_gap_days']:.1f}",
            f"${e['revenue_exposure_usd']:,.0f}",
        )
    console.print(exp_tbl)

    alloc_tbl = Table(title="Exact Branch-and-Bound MILP Multi-Sourcing Reroute Plan")
    alloc_tbl.add_column("Lane ID", style="cyan")
    alloc_tbl.add_column("Mode", style="magenta")
    alloc_tbl.add_column("Units Shipped", justify="right")
    alloc_tbl.add_column("Lead Time (d)", justify="right")
    alloc_tbl.add_column("Landed Cost ($)", justify="right", style="green")
    alloc_tbl.add_column("Scope-3 CO2 (kg)", justify="right")

    for a in plan["allocations"]:
        alloc_tbl.add_row(
            a["lane_id"],
            a["mode"],
            f"{a['units_shipped']:,.1f}",
            f"{a['effective_lead_time_days']:.1f}",
            f"${a['landed_cost_usd']:,.2f}",
            f"{a['co2_kg']:,.1f}",
        )
    console.print(alloc_tbl)
    console.print(
        Panel(
            f"[bold green]MILP Status:[/bold green] {plan['status']} | "
            f"Fulfilled: {plan['fulfilled_units']:,.0f}/{plan['demand_units']:,.0f} units | "
            f"Landed Cost: [bold]${plan['total_landed_cost_usd']:,.2f}[/bold]\n"
            f"Weighted Lead Time: {plan['weighted_lead_time_days']:.2f}d | "
            f"B&B Nodes Explored: {plan['branch_and_bound_nodes']} | "
            f"Solve Time: {plan['solve_latency_ms']:.2f} ms",
            title="Global Optimality Certificate",
        )
    )


@app.command()
def pareto(
    disruption: str = typer.Option("red_sea_and_kaohsiung_compound", help="Disruption scenario ID"),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Sweep the 3-objective Cost vs. Lead-Time vs. Scope-3 Carbon Pareto frontier."""
    dt = ChronosDigitalTwin()
    pts = dt.compute_pareto(disruption_id=disruption)
    if json_out:
        console.print_json(json.dumps([p.model_dump() for p in pts]))
        return

    tbl = Table(title=f"Pareto Frontier Sweep — {disruption}")
    tbl.add_column("Executive Regime", style="cyan")
    tbl.add_column("Total Landed Cost", justify="right", style="green")
    tbl.add_column("Weighted Lead Time", justify="right")
    tbl.add_column("Scope-3 Carbon", justify="right")
    tbl.add_column("Solve Time", justify="right")

    for pt in pts:
        p = pt.plan
        tbl.add_row(
            pt.profile_name,
            f"${p.total_landed_cost_usd:,.2f}",
            f"{p.weighted_lead_time_days:.2f} days",
            f"{p.total_co2_kg:,.1f} kg CO2e",
            f"{p.solve_latency_ms:.2f} ms",
        )
    console.print(tbl)


@app.command()
def montecarlo(
    trials: int = typer.Option(500, help="Number of stochastic disruption trials"),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON output"),
) -> None:
    """Run Monte Carlo VaR95 & Conditional Value-at-Risk (CVaR95) tail-loss benchmark."""
    dt = ChronosDigitalTwin()
    rep = dt.simulate_cvar(trials=trials)
    if json_out:
        console.print_json(json.dumps(rep.model_dump()))
        return

    tbl = Table(title=f"Stochastic Supply-Chain Tail-Risk Benchmark ({trials} Monte Carlo Trials)")
    tbl.add_column("Metric", style="cyan")
    tbl.add_column("Fragile Single-Source", justify="right", style="red")
    tbl.add_column("ChronosMesh MILP Resilient", justify="right", style="bold green")

    tbl.add_row(
        "Mean Total Cost",
        f"${rep.baseline_mean_cost_usd:,.2f}",
        f"${rep.optimized_mean_cost_usd:,.2f}",
    )
    tbl.add_row(
        "95% Value-at-Risk (VaR95)",
        f"${rep.baseline_var95_usd:,.2f}",
        f"${rep.optimized_var95_usd:,.2f}",
    )
    tbl.add_row(
        "95% Expected Shortfall (CVaR95)",
        f"${rep.baseline_cvar95_usd:,.2f}",
        f"${rep.optimized_cvar95_usd:,.2f}",
    )
    tbl.add_row(
        "Demand Fill-Rate Service Level",
        f"{rep.baseline_fill_rate_pct:.2f}%",
        f"{rep.optimized_fill_rate_pct:.2f}%",
    )
    console.print(tbl)
    console.print(
        f"\n[bold green]Tail-Risk CVaR95 Reduction:[/bold green] "
        f"${rep.expected_cvar_reduction_usd:,.2f} ({rep.expected_cvar_reduction_pct:.1f}% reduction)"
    )


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind host"),
    port: int = typer.Option(8010, help="Bind port"),
) -> None:
    """Launch the ChronosMesh Digital-Twin API & React Optimization Console."""
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    app()

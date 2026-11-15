import { useEffect, useState } from "react";

interface Allocation {
  lane_id: string;
  mode: string;
  units_shipped: number;
  effective_lead_time_days: number;
  landed_cost_usd: number;
  co2_kg: number;
}

interface EvalResult {
  shock: { headline: string; severity_score: number };
  risk_exposure: Array<{
    name: string;
    tier: string;
    effective_ttr_days: number;
    effective_tts_days: number;
    revenue_exposure_usd: number;
  }>;
  optimal_plan: {
    status: string;
    fulfilled_units: number;
    demand_units: number;
    total_landed_cost_usd: number;
    weighted_lead_time_days: number;
    total_co2_kg: number;
    branch_and_bound_nodes: number;
    solve_latency_ms: number;
    allocations: Allocation[];
  };
  recommended_safety_stock_units: number;
}

interface MonteCarloResult {
  trials: number;
  baseline_cvar95_usd: number;
  optimized_cvar95_usd: number;
  baseline_fill_rate_pct: number;
  optimized_fill_rate_pct: number;
  expected_cvar_reduction_pct: number;
}

export function App() {
  const [scenario, setScenario] = useState("red_sea_and_kaohsiung_compound");
  const [data, setData] = useState<EvalResult | null>(null);
  const [mc, setMc] = useState<MonteCarloResult | null>(null);
  const [advisory, setAdvisory] = useState(
    "URGENT BULLETIN: Red Sea corridor closed; Kaohsiung wafer fab reports 55% output curtailment and 15% tariff surcharge."
  );

  const runOptimize = async (scId: string) => {
    setScenario(scId);
    const r = await fetch("/api/v1/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ disruption_id: scId, demand_units: 1100 }),
    });
    setData((await r.json()) as EvalResult);
  };

  const runNeuroParse = async () => {
    const r = await fetch("/api/v1/neuro/parse-and-solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ advisory_text: advisory, demand_units: 1100 }),
    });
    const j = await r.json();
    setData({
      shock: j.compiled_shock,
      risk_exposure: j.risk_exposure,
      optimal_plan: j.optimal_plan,
      recommended_safety_stock_units: 195,
    });
  };

  const runMonteCarlo = async () => {
    const r = await fetch("/api/v1/risk/montecarlo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trials: 400 }),
    });
    setMc((await r.json()) as MonteCarloResult);
  };

  useEffect(() => {
    void runOptimize(scenario);
    void runMonteCarlo();
  }, []);

  return (
    <div className="wrap">
      <header className="hdr">
        <div>
          <h1 style={{ margin: 0, fontSize: "1.35rem" }}>
            ChronosMesh — Neuro-Symbolic Supply-Chain Digital Twin
          </h1>
          <div style={{ color: "#8aa4bf", fontSize: "0.84rem", marginTop: 4 }}>
            Multi-Tier Simchi-Levi Contagion Graph · Exact Branch-and-Bound MILP Solver · Monte Carlo CVaR95
          </div>
        </div>
        <div>
          <button className="btn" onClick={() => void runOptimize("nominal_operations")}>
            Nominal
          </button>
          <button className="btn" onClick={() => void runOptimize("red_sea_maritime_blockade")}>
            Red Sea Blockade
          </button>
          <button
            className="btn"
            onClick={() => void runOptimize("red_sea_and_kaohsiung_compound")}
          >
            Compound Crisis
          </button>
        </div>
      </header>

      <div className="grid-4">
        <div className="card">
          <div style={{ color: "#8aa4bf", fontSize: "0.75rem" }}>MILP OPTIMAL LANDED COST</div>
          <div style={{ fontSize: "1.45rem", fontWeight: 700, marginTop: 6 }}>
            ${data?.optimal_plan.total_landed_cost_usd.toLocaleString() ?? "..."}
          </div>
          <div style={{ color: "#2dd4bf", fontSize: "0.76rem", marginTop: 4 }}>
            {data?.optimal_plan.status} ({data?.optimal_plan.solve_latency_ms} ms)
          </div>
        </div>
        <div className="card">
          <div style={{ color: "#8aa4bf", fontSize: "0.75rem" }}>WEIGHTED SLA LEAD TIME</div>
          <div style={{ fontSize: "1.45rem", fontWeight: 700, marginTop: 6 }}>
            {data?.optimal_plan.weighted_lead_time_days ?? "..."} days
          </div>
          <div style={{ color: "#8aa4bf", fontSize: "0.76rem", marginTop: 4 }}>
            B&amp;B Nodes: {data?.optimal_plan.branch_and_bound_nodes}
          </div>
        </div>
        <div className="card">
          <div style={{ color: "#8aa4bf", fontSize: "0.75rem" }}>CVaR95 TAIL-RISK REDUCTION</div>
          <div style={{ fontSize: "1.45rem", fontWeight: 700, marginTop: 6, color: "#2dd4bf" }}>
            {mc ? `-${mc.expected_cvar_reduction_pct}%` : "..."}
          </div>
          <div style={{ color: "#8aa4bf", fontSize: "0.76rem", marginTop: 4 }}>
            Fill Rate: {mc?.optimized_fill_rate_pct}% vs {mc?.baseline_fill_rate_pct}%
          </div>
        </div>
        <div className="card">
          <div style={{ color: "#8aa4bf", fontSize: "0.75rem" }}>MULTI-ECHELON SAFETY STOCK</div>
          <div style={{ fontSize: "1.45rem", fontWeight: 700, marginTop: 6 }}>
            {data?.recommended_safety_stock_units ?? "..."} units
          </div>
          <div style={{ color: "#8aa4bf", fontSize: "0.76rem", marginTop: 4 }}>
            98% Cycle Service Level
          </div>
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Neuro-Symbolic Unstructured Disruption Compiler</h3>
        <textarea value={advisory} onChange={(e) => setAdvisory(e.target.value)} />
        <div style={{ marginTop: 10 }}>
          <button className="btn" onClick={() => void runNeuroParse()}>
            Compile Advisory into MILP Constraints &amp; Solve
          </button>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Simchi-Levi Contagion Exposure (TTR vs TTS)</h3>
          <table>
            <thead>
              <tr>
                <th>Node</th>
                <th>TTR</th>
                <th>TTS</th>
                <th>Revenue at Risk</th>
              </tr>
            </thead>
            <tbody>
              {data?.risk_exposure.map((e) => (
                <tr key={e.name}>
                  <td>{e.name}</td>
                  <td>{e.effective_ttr_days}d</td>
                  <td>{e.effective_tts_days}d</td>
                  <td>${e.revenue_exposure_usd.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>Globally Optimal MILP Multi-Sourcing Allocation</h3>
          <table>
            <thead>
              <tr>
                <th>Lane</th>
                <th>Mode</th>
                <th>Units</th>
                <th>Lead Time</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {data?.optimal_plan.allocations.map((a) => (
                <tr key={a.lane_id}>
                  <td>{a.lane_id}</td>
                  <td>{a.mode}</td>
                  <td>{a.units_shipped}</td>
                  <td>{a.effective_lead_time_days}d</td>
                  <td>${a.landed_cost_usd.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

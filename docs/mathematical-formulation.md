# Mathematical Formulation & Operations Research Specification

## 1. Neuro-Symbolic Architectural Separation

Large Language Models excel at parsing unstructured geopolitical, customs, and supplier force-majeure advisories, but fail catastrophically when asked to directly output feasible multi-echelon shipment quantities under coupled capacity, fixed-charge, and SLA constraints.

`ChronosMesh` enforces a strict **Neuro-Symbolic boundary**:
1. **Symbolic Compilation (`src/chronos_mesh/neuro/`)**: Unstructured text $\mathcal{T}$ is compiled into a formal parameter patch $\Delta = (\alpha_s, \mathcal{B}_{\text{lanes}}, \delta_{\ell}, \tau_s)$.
2. **Exact Mixed-Integer Optimization (`src/chronos_mesh/optimizer/`)**: A Two-Phase Simplex + Best-First Branch-and-Bound MILP solver computes globally optimal primal allocations $(q^*, y^*, u^*)$.

## 2. Fixed-Charge Multi-Sourcing MILP Formulation

Let $\mathcal{L}$ be the set of transport corridors and $\mathcal{S}$ the set of upstream facilities. Decision variables are continuous lane flows $q_\ell \ge 0$, binary charter/corridor activations $y_\ell \in \{0, 1\}$, and unmet demand slack $u \ge 0$:

$$\min_{q, y, u} \sum_{\ell \in \mathcal{L}} \Big( w_c c_\ell(\Delta) + w_t d_\ell(\Delta) + w_g e_\ell \Big) q_\ell + w_c \sum_{\ell \in \mathcal{L}} F_\ell y_\ell + P \cdot u$$

subject to:
1. **Demand Conservation**: $\sum_{\ell \in \mathcal{L}} q_\ell + u = D$
2. **Big-$M$ Fixed-Charge Activation**: $q_\ell - M_\ell y_\ell \le 0 \quad \forall \ell \in \mathcal{L}$
3. **Shocked Facility Capacity**: $\sum_{\ell \in \text{out}(s)} q_\ell \le \alpha_s K_s \quad \forall s \in \mathcal{S}$
4. **Anti-Concentration Diversification**: $\sum_{\ell \in \text{out}(s)} q_\ell \le \theta_{\max} D \quad (\theta_{\max} = 0.65)$
5. **Portfolio SLA Lead-Time Ceiling**: $\sum_{\ell \in \mathcal{L}} \big(d_\ell(\Delta) - L_{\max}\big) q_\ell \le 0$
6. **Integrality**: $y_\ell \in \{0, 1\}, \; q_\ell \ge 0, \; u \ge 0$

## 3. Simchi-Levi Risk Exposure Index & Safety Stock

- **Risk Exposure Index (`REI`)**: For each node $v$ with effective recovery time $\text{TTR}_v$ and buffered survival window $\text{TTS}_v$:
  $$\text{Exposure}(v) = R_v \cdot \max\big(0, \; \text{TTR}_v - \text{TTS}_v\big)$$
- **Joint Demand & Lead-Time Uncertainty Safety Stock**:
  $$SS = z_{\alpha}\sqrt{\mu_L \sigma_D^2 + \mu_D^2 \sigma_L^2}$$
- **95% Conditional Value-at-Risk (`CVaR95`)**: Expected cost conditional on falling in the worst $5\%$ disruption tail across $N$ Monte Carlo scenarios.

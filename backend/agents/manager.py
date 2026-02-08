#!/usr/bin/env python3
"""
AI Agent Orchestration via LangGraph.

Three-agent pipeline:
  1. MarketAgent    — gathers (mock) market data & sentiment
  2. ExecutionAgent — runs QUBO optimization on the data
  3. RiskAgent      — pre-flight checks before signing the tx

The graph: Market → Execution → Risk → (approve | reject)

Author: Valentin Israel — ETH Oxford Hackathon 2026
"""

import json
import logging
import time
import httpx  # For calling external AI Worker
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional

import numpy as np

# LangGraph imports
from langgraph.graph import END, StateGraph

# Local
from quantum.optimizer import (
    Asset,
    OptimizationResult,
    PortfolioQUBO,
    QUBOConfig,
    make_test_universe,
)
from quantum.rng import run_quantum_rng_local

AI_ENDPOINT = "https://cashxchain-ai-v1.cashxchain.workers.dev/"

def call_ai_agent(context: str, instruction: str, fallback: str) -> str:
    """
    Calls the external CashXChain AI Worker to generate reasoning/analysis.
    Falls back to the provided 'fallback' string on error or timeout.
    """
    try:
        full_prompt = (
            f"You are an expert crypto portfolio analyst agent for CashXChain.\n"
            f"Context Data:\n{context}\n\n"
            f"Instructions: {instruction}\n"
            f"Provide a concise, professional, and data-driven explanation."
        )
        
        # Use a longer timeout for the AI
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(AI_ENDPOINT, json={"prompt": full_prompt})
            resp.raise_for_status()
            data = resp.json()
            # Expecting Cloudflare Worker response: {"result": {"response": "..."}}
            # or direct if the worker changed. Based on user curl:
            # {"model":..., "result": {"response": "..."}}
            ai_text = data.get("result", {}).get("response", "")
            if not ai_text:
                 # fallback if structure differs
                 ai_text = data.get("response", "")
            
            if ai_text:
                return ai_text.strip()
            
    except Exception as e:
        logging.getLogger("uvicorn").warning(f"AI Agent call failed: {e}")
    
    return fallback


try:
    from core.market_data import MarketDataFetcher

    HAS_MARKET_DATA = True
except ImportError:
    HAS_MARKET_DATA = False

try:
    from core.slippage import (
        SlippageEstimate,
        estimate_rebalance_slippage,
        format_slippage_report,
    )

    HAS_SLIPPAGE = True
except ImportError:
    HAS_SLIPPAGE = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared state that flows through the graph
# ---------------------------------------------------------------------------


@dataclass
class PipelineState:
    """Mutable state passed between agents."""

    # Inputs
    user_id: str = ""
    risk_tolerance: float = 0.5  # 0 = conservative, 1 = aggressive
    use_mock: bool = False  # force mock market data

    # MarketAgent fills these
    assets: List[Asset] = field(default_factory=list)
    cov_matrix: Optional[np.ndarray] = None
    market_summary: str = ""
    market_timestamp: float = 0.0

    # ExecutionAgent fills these
    optimization_result: Optional[OptimizationResult] = None
    slippage_estimates: Dict[str, Any] = field(default_factory=dict)  # per-asset impact

    # RiskAgent fills these
    risk_approved: bool = False
    risk_report: str = ""
    risk_checks: Dict[str, bool] = field(default_factory=dict)

    # Explainable AI (XAI): Reasoning from each agent
    reasoning: Dict[str, str] = field(default_factory=dict)  # agent_name -> explanation text

    # Final
    status: Literal["pending", "approved", "rejected", "error", "pending_approval"] = "pending"
    requires_approval: bool = False  # multi-sig flag
    approval_reasons: List[str] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)

    def log(self, agent: str, msg: str):
        entry = f"[{agent}] {msg}"
        self.logs.append(entry)
        logger.info(entry)


# ---------------------------------------------------------------------------
# Helper: state ↔ dict conversion for LangGraph
# ---------------------------------------------------------------------------


def state_to_dict(state: PipelineState) -> Dict[str, Any]:
    """Serialize PipelineState to a JSON-safe dict for LangGraph."""
    d = {}
    d["user_id"] = state.user_id
    d["risk_tolerance"] = state.risk_tolerance
    d["use_mock"] = state.use_mock
    d["assets"] = [(a.symbol, a.expected_return, a.max_weight) for a in state.assets]
    d["cov_matrix"] = state.cov_matrix.tolist() if state.cov_matrix is not None else None
    d["market_summary"] = state.market_summary
    d["market_timestamp"] = state.market_timestamp
    if state.optimization_result:
        d["optimization_result"] = {
            "allocation": state.optimization_result.allocation,
            "weights": state.optimization_result.weights,
            "expected_return": state.optimization_result.expected_return,
            "expected_risk": state.optimization_result.expected_risk,
            "energy": state.optimization_result.energy,
            "solver_used": state.optimization_result.solver_used,
            "solver_time_s": state.optimization_result.solver_time_s,
            "feasible": state.optimization_result.feasible,
            "reason": state.optimization_result.reason,
        }
    else:
        d["optimization_result"] = None
    # Slippage estimates (serialized)
    d["slippage_estimates"] = state.slippage_estimates
    d["risk_approved"] = state.risk_approved
    d["risk_report"] = state.risk_report
    d["risk_checks"] = state.risk_checks
    d["reasoning"] = state.reasoning  # XAI: explanations from each agent
    d["status"] = state.status
    d["requires_approval"] = state.requires_approval
    d["approval_reasons"] = state.approval_reasons
    d["logs"] = state.logs
    return d


def dict_to_state(d: Dict[str, Any]) -> PipelineState:
    """Deserialize dict back to PipelineState."""
    state = PipelineState()
    state.user_id = d.get("user_id", "")
    state.risk_tolerance = d.get("risk_tolerance", 0.5)
    state.use_mock = d.get("use_mock", False)
    if d.get("assets"):
        state.assets = [
            Asset(symbol=a[0], expected_return=a[1], max_weight=a[2]) for a in d["assets"]
        ]
    if d.get("cov_matrix") is not None:
        state.cov_matrix = np.array(d["cov_matrix"])
    state.market_summary = d.get("market_summary", "")
    state.market_timestamp = d.get("market_timestamp", 0.0)
    if d.get("optimization_result"):
        opt = d["optimization_result"]
        state.optimization_result = OptimizationResult(
            allocation=opt["allocation"],
            weights=opt["weights"],
            expected_return=opt["expected_return"],
            expected_risk=opt["expected_risk"],
            energy=opt["energy"],
            solver_used=opt["solver_used"],
            solver_time_s=opt["solver_time_s"],
            feasible=opt["feasible"],
            reason=opt.get("reason", ""),
        )
    state.slippage_estimates = d.get("slippage_estimates", {})
    state.risk_approved = d.get("risk_approved", False)
    state.risk_report = d.get("risk_report", "")
    state.risk_checks = d.get("risk_checks", {})
    state.reasoning = d.get("reasoning", {})  # XAI: explanations from each agent
    state.status = d.get("status", "pending")
    state.requires_approval = d.get("requires_approval", False)
    state.approval_reasons = d.get("approval_reasons", [])
    state.logs = d.get("logs", [])
    return state


# ---------------------------------------------------------------------------
# Agent 1: Market Intelligence Agent
# ---------------------------------------------------------------------------


def market_agent(state_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Gather market data, compute expected returns & covariance.
    For the hackathon we use mock data; in production this would call
    CoinGecko / Pyth / Chainlink oracles.
    """
    state = dict_to_state(state_dict)
    state.log("MarketAgent", "Collecting market intelligence …")

    # Try real CoinGecko data first, fallback to mock
    use_real = False
    if HAS_MARKET_DATA and not state.use_mock:
        try:
            fetcher = MarketDataFetcher()
            assets, cov = fetcher.fetch_prices_and_returns(days=30)
            use_real = True
            state.log("MarketAgent", " Using REAL market data (CoinGecko 30d)")
        except Exception as e:
            state.log("MarketAgent", f" CoinGecko failed ({e}), using mock data")

    if not use_real:
        assets, cov = make_test_universe()
        state.log("MarketAgent", "Using mock market data (5 assets)")

    # Sentiment adjustment based on risk tolerance
    sentiment_boost = (state.risk_tolerance - 0.5) * 0.05
    for a in assets:
        a.expected_return += sentiment_boost + np.random.normal(0, 0.01)

    state.assets = assets
    state.cov_matrix = cov
    state.market_timestamp = time.time()
    state.market_summary = (
        f"Fetched {len(assets)} assets. "
        f"Top expected return: {max(a.expected_return for a in assets):.2%} "
        f"(sentiment adj: {sentiment_boost:+.2%})"
    )
    state.log("MarketAgent", state.market_summary)
    state.log("MarketAgent", f"Assets: {[a.symbol for a in assets]}")
    
    # ── Explainable AI: Generate reasoning for this decision ──
    asset_details = []
    for a in assets:
        vol = np.sqrt(state.cov_matrix[assets.index(a), assets.index(a)])
        asset_details.append(f"{a.symbol} (ret={a.expected_return:.2%}, vol={vol:.2%})")
    
    # Raw data context for the AI
    context_str = (
        f"Assets Analyzed: {len(assets)}\n"
        f"Top Expected Return: {max(a.expected_return for a in assets):.2%}\n"
        f"User Risk Tolerance: {state.risk_tolerance:.1%} (0=Conservative, 1=Aggressive)\n"
        f"Sentiment Adjustment: {sentiment_boost:+.2%}\n"
        f"Asset Metrics: {'; '.join(asset_details)}\n"
        f"Data Source: {'Real (CoinGecko)' if use_real else 'Mock'}"
    )
    
    # Fallback template
    fallback_text = (
        f"Market Intelligence Report:\n"
        f"  • Collected {len(assets)} assets with expected returns and covariance matrix\n"
        f"  • Top return: {max(a.expected_return for a in assets):.2%}\n"
        f"  • Sentiment adjustment: {sentiment_boost:+.2%} based on risk tolerance {state.risk_tolerance:.1%}\n"
        f"  • Assets: {', '.join(asset_details)}\n"
        f"  • Data source: {'Real (CoinGecko)' if use_real else 'Mock'}\n"
        f"  • Timestamp: {state.market_timestamp:.0f}"
    )

    # Call AI (concise summary)
    ai_instruction = (
        "Summarize the market conditions for the user's wallet analysis. "
        "Mention the top performing assets and how the user's risk tolerance influenced the view."
    )
    state.reasoning["MarketAgent"] = call_ai_agent(context_str, ai_instruction, fallback_text)

    return state_to_dict(state)


# ---------------------------------------------------------------------------
# Agent 2: Execution / Quantum-Optimization Agent
# ---------------------------------------------------------------------------


def execution_agent(state_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build and solve the QUBO model for portfolio optimization.
    """
    state = dict_to_state(state_dict)
    state.log("ExecutionAgent", "Building QUBO model …")

    if not state.assets or state.cov_matrix is None:
        state.log("ExecutionAgent", "ERROR: No market data available")
        state.status = "error"
        return state_to_dict(state)

    # Adaptive target based on risk tolerance
    target = max(2, min(len(state.assets), int(len(state.assets) * state.risk_tolerance) + 1))

    cfg = QUBOConfig(
        lambda_return=1.0,
        lambda_risk=max(0.1, 1.0 - state.risk_tolerance),
        lambda_budget=2.0,
        target_assets=target,
        num_reads=200,
        use_qpu=False,  # flip to True for real QPU
    )

    state.log(
        "ExecutionAgent",
        f"QUBO params: target={target}, λ_risk={cfg.lambda_risk:.2f}, λ_ret={cfg.lambda_return:.2f}",
    )
    state.log("ExecutionAgent", "Quantum Solver active … running simulated annealing")

    optimizer = PortfolioQUBO(state.assets, state.cov_matrix, cfg)
    result = optimizer.solve()
    state.optimization_result = result

    # ── Quantum RNG timing randomization (anti-front-running) ──
    # Add a random delay (0–2s) derived from quantum RNG to prevent
    # predictable rebalancing timing that MEV bots could exploit.
    rng_result = run_quantum_rng_local(shots=16)
    ones_count = rng_result.get("1", 0)
    random_delay_s = (ones_count / 16.0) * 2.0  # 0–2 seconds
    state.log(
        "ExecutionAgent",
        f"⏳ Quantum RNG timing jitter: {random_delay_s:.2f}s "
        f"(anti-front-running, {ones_count}/16 ones)"
    )
    time.sleep(random_delay_s)

    selected = [s for s, v in result.allocation.items() if v == 1]
    state.log(
        "ExecutionAgent",
        f"Optimization complete in {result.solver_time_s:.3f}s: "
        f"selected={selected}, E(r)={result.expected_return:.4f}, "
        f"σ={result.expected_risk:.4f}",
    )

    # ── Explainable AI: Generate reasoning for optimization ──
    rebalance_details = []
    for sym, alloc in result.allocation.items():
        if alloc == 1:
            weight = result.weights.get(sym, 0.0)
            rebalance_details.append(f"{sym}: +{weight:.1%}")
    
    context_str = (
        f"Selected Assets: {', '.join(selected)}\n"
        f"Allocations: {', '.join(rebalance_details)}\n"
        f"Portfolio Metrics: Expected Return E[r]={result.expected_return:.2%}, Risk σ={result.expected_risk:.2%}\n"
        f"User ID/Wallet: {state.user_id}\n"
        f"Solver: {result.solver_used} (Time: {result.solver_time_s:.3f}s)\n"
        f"Energy: {result.energy:.6f}\n"
        f"Feasible: {result.feasible}"
    )

    fallback_text = (
        f"Quantum QUBO Optimization Result:\n"
        f"  • Selected Assets: {', '.join(selected)}\n"
        f"  • Weights: {', '.join(rebalance_details)}\n"
        f"  • Expected Return (E[r]): {result.expected_return:.2%}\n"
        f"  • Expected Risk (σ): {result.expected_risk:.2%}\n"
        f"  • Optimization Energy: {result.energy:.6f}\n"
        f"  • Solver: {result.solver_used} in {result.solver_time_s:.3f}s\n"
        f"  • Feasible: {'Yes' if result.feasible else 'No'}\n"
        f"  • Reason: {result.reason}"
    )

    ai_instruction = (
        f"Explain why this portfolio allocation (Assets: {', '.join(selected)}) is optimal for the user (Wallet: {state.user_id}). "
        "Highlight the trade-off between return and risk. Mention the Quantum QUBO solver's role."
    )
    
    state.reasoning["ExecutionAgent"] = call_ai_agent(context_str, ai_instruction, fallback_text)

    # ── Market Impact / Slippage estimation (Almgren-Chriss) ──
    # Compute min_out for each swap BEFORE submitting to chain.
    # The Move contract will enforce: assert!(output >= min_out)
    if HAS_SLIPPAGE and result.allocation:
        try:
            estimates = estimate_rebalance_slippage(
                allocation=result.allocation,
                weights=result.weights,
                portfolio_value_usd=50_000,  # default; override via state in production
            )
            # Serialize for state transport
            state.slippage_estimates = {
                sym: {
                    "order_size_usd": e.order_size_usd,
                    "daily_volume_usd": e.daily_volume_usd,
                    "volume_fraction": e.volume_fraction,
                    "raw_impact_pct": e.raw_impact_pct,
                    "total_slippage_pct": e.total_slippage_pct,
                    "min_out_usd": e.min_out_usd,
                    "min_out_mist": e.min_out_mist,
                    "exceeds_max_impact": e.exceeds_max_impact,
                    "alpha": e.alpha,
                    "beta": e.beta,
                }
                for sym, e in estimates.items()
            }
            report = format_slippage_report(estimates)
            state.log("ExecutionAgent", report)

            any_exceeds = any(e.exceeds_max_impact for e in estimates.values())
            if any_exceeds:
                state.log(
                    "ExecutionAgent",
                    "WARNING: Some swaps exceed max impact threshold (5%)"
                )
        except Exception as e:
            state.log("ExecutionAgent", f"Slippage estimation failed: {e}")
    else:
        state.log("ExecutionAgent", "Slippage model not available — skipping impact analysis")

    return state_to_dict(state)


# ---------------------------------------------------------------------------
# Agent 3: Risk Management Agent (Pre-Flight Check)
# ---------------------------------------------------------------------------

# Guardrail constants
MAX_POSITION_WEIGHT = 0.40  # no single asset > 40%
MAX_PORTFOLIO_RISK = 0.45  # annualized σ cap (crypto-appropriate)
MIN_EXPECTED_RETURN = 0.01  # at least 1% expected return
MAX_SOLVER_TIME_S = 5.0  # solver must be fast
MAX_DAILY_VOLUME_USD = 1_000_000  # placeholder cap

# Multi-sig approval threshold — trades above this need human sign-off
APPROVAL_THRESHOLD_USD = 50_000  # trades above $50k require approval
APPROVAL_RISK_THRESHOLD = 0.30   # or risk σ > 30% requires approval


def risk_agent(state_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pre-flight checks before signing the on-chain transaction.
    Enforces hard guardrails that match Korbinian's on-chain ExecutionGuardrails.
    """
    state = dict_to_state(state_dict)
    state.log("RiskAgent", "Running pre-flight checks …")

    opt = state.optimization_result
    if opt is None:
        state.risk_approved = False
        state.risk_report = "No optimization result to evaluate."
        state.status = "error"
        return state_to_dict(state)

    checks = {}

    # Check 1: Feasibility from optimizer
    checks["optimizer_feasible"] = opt.feasible
    if not opt.feasible:
        state.log("RiskAgent", f" Optimizer infeasible: {opt.reason}")

    # Check 2: Max position size
    max_w = max(opt.weights.values()) if opt.weights else 0.0
    checks["position_size_ok"] = max_w <= MAX_POSITION_WEIGHT
    if not checks["position_size_ok"]:
        state.log("RiskAgent", f" Position too large: {max_w:.2%} > {MAX_POSITION_WEIGHT:.2%}")

    # Check 3: Portfolio risk cap
    checks["risk_within_limit"] = opt.expected_risk <= MAX_PORTFOLIO_RISK
    if not checks["risk_within_limit"]:
        state.log(
            "RiskAgent",
            f" Portfolio risk too high: {opt.expected_risk:.4f} > {MAX_PORTFOLIO_RISK}",
        )

    # Check 4: Minimum expected return
    checks["return_sufficient"] = opt.expected_return >= MIN_EXPECTED_RETURN
    if not checks["return_sufficient"]:
        state.log(
            "RiskAgent",
            f" Expected return too low: {opt.expected_return:.4f} < {MIN_EXPECTED_RETURN}",
        )

    # Check 5: Solver speed
    checks["solver_fast_enough"] = opt.solver_time_s <= MAX_SOLVER_TIME_S
    if not checks["solver_fast_enough"]:
        state.log(
            "RiskAgent", f" Solver too slow: {opt.solver_time_s:.3f}s > {MAX_SOLVER_TIME_S}s"
        )

    # Check 6: At least one asset selected
    n_selected = sum(1 for v in opt.allocation.values() if v == 1)
    checks["assets_selected"] = n_selected >= 1
    if not checks["assets_selected"]:
        state.log("RiskAgent", " No assets selected")

    # Check 7: Slippage / market impact within bounds
    if state.slippage_estimates:
        any_exceeds = any(
            e.get("exceeds_max_impact", False)
            for e in state.slippage_estimates.values()
        )
        checks["slippage_acceptable"] = not any_exceeds
        if any_exceeds:
            bad = [s for s, e in state.slippage_estimates.items() if e.get("exceeds_max_impact")]
            state.log("RiskAgent", f" Market impact too high for: {bad}")
        else:
            avg_slip = np.mean([
                e.get("total_slippage_pct", 0)
                for e in state.slippage_estimates.values()
            ])
            state.log("RiskAgent", f" Slippage OK (avg {avg_slip:.4%} per swap)")
    else:
        checks["slippage_acceptable"] = True  # no model = pass (graceful)

    # Aggregate
    all_passed = all(checks.values())
    state.risk_checks = checks
    state.risk_approved = all_passed

    # ── Explainable AI: Generate detailed reasoning for all checks ──
    reasoning_lines = ["Risk Management Pre-Flight Checks:"]
    for check_name, passed in checks.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        if check_name == "optimizer_feasible":
            reasoning_lines.append(f"  {status} — Optimizer feasibility: {opt.feasible}")
        elif check_name == "position_size_ok":
            max_w = max(opt.weights.values()) if opt.weights else 0.0
            reasoning_lines.append(
                f"  {status} — Max position {max_w:.2%} ≤ limit {MAX_POSITION_WEIGHT:.2%}"
            )
        elif check_name == "risk_within_limit":
            reasoning_lines.append(
                f"  {status} — Portfolio risk σ={opt.expected_risk:.4f} "
                f"≤ cap {MAX_PORTFOLIO_RISK}"
            )
        elif check_name == "return_sufficient":
            reasoning_lines.append(
                f"  {status} — Expected return {opt.expected_return:.4f} "
                f"≥ minimum {MIN_EXPECTED_RETURN}"
            )
        elif check_name == "solver_fast_enough":
            reasoning_lines.append(
                f"  {status} — Solver time {opt.solver_time_s:.3f}s "
                f"≤ limit {MAX_SOLVER_TIME_S}s"
            )
        elif check_name == "assets_selected":
            n_sel = sum(1 for v in opt.allocation.values() if v == 1)
            reasoning_lines.append(f"  {status} — Assets selected: {n_sel}")
        elif check_name == "slippage_acceptable":
            if state.slippage_estimates:
                avg_slip = np.mean([
                    e.get("total_slippage_pct", 0)
                    for e in state.slippage_estimates.values()
                ])
                reasoning_lines.append(
                    f"  {status} — Avg slippage {avg_slip:.4%} acceptable"
                )
            else:
                reasoning_lines.append(f"  {status} — No slippage model (graceful pass)")
    
    fallback_text = "\n".join(reasoning_lines)
    
    context_str = fallback_text + f"\nOverall Passed: {all_passed}"
    if not all_passed:
        failed = [k for k, v in checks.items() if not v]
        context_str += f"\nFailed Checks: {failed}"

    ai_instruction = (
        "Review the Risk Management Pre-Flight Checks for the user's wallet. "
        "Confirm if the trade is safe to execute or why it was rejected. "
        "Be strict but helpful."
    )
    
    state.reasoning["RiskAgent"] = call_ai_agent(context_str, ai_instruction, fallback_text)

    if all_passed:
        # ── Multi-sig approval threshold check ──
        approval_reasons = []

        # Check if trade value exceeds threshold (estimate based on weights)
        total_weight_active = sum(w for w in opt.weights.values() if w > 0)
        estimated_value = total_weight_active * MAX_DAILY_VOLUME_USD
        if estimated_value > APPROVAL_THRESHOLD_USD:
            approval_reasons.append(
                f"Estimated trade value ${estimated_value:,.0f} > "
                f"threshold ${APPROVAL_THRESHOLD_USD:,.0f}"
            )

        # Check if portfolio risk is close to limit
        if opt.expected_risk > APPROVAL_RISK_THRESHOLD:
            approval_reasons.append(
                f"Portfolio risk σ={opt.expected_risk:.4f} > "
                f"approval threshold {APPROVAL_RISK_THRESHOLD}"
            )

        if approval_reasons:
            state.status = "pending_approval"
            state.requires_approval = True
            state.approval_reasons = approval_reasons
            state.risk_report = (
                f"All {len(checks)} checks passed but requires human approval: "
                + "; ".join(approval_reasons)
            )
            state.log("RiskAgent", f"  PENDING APPROVAL — {'; '.join(approval_reasons)}")
        else:
            state.status = "approved"
            state.risk_report = f"All {len(checks)} checks passed. Transaction approved."
            state.log("RiskAgent", " All checks passed — APPROVED for on-chain execution")
    else:
        state.status = "rejected"
        failed = [k for k, v in checks.items() if not v]
        state.risk_report = f"Failed checks: {failed}"
        state.log("RiskAgent", f" REJECTED — failed: {failed}")

    return state_to_dict(state)


# ---------------------------------------------------------------------------
# LangGraph Workflow
# ---------------------------------------------------------------------------


def build_agent_graph() -> StateGraph:
    """
    Build the LangGraph:
        MarketAgent → ExecutionAgent → RiskAgent → END
    """
    workflow = StateGraph(dict)

    workflow.add_node("market_agent", market_agent)
    workflow.add_node("execution_agent", execution_agent)
    workflow.add_node("risk_agent", risk_agent)

    workflow.set_entry_point("market_agent")
    workflow.add_edge("market_agent", "execution_agent")
    workflow.add_edge("execution_agent", "risk_agent")
    workflow.add_edge("risk_agent", END)

    return workflow.compile()


def run_pipeline(
    user_id: str = "demo-user",
    risk_tolerance: float = 0.5,
    use_mock: bool = False,
) -> PipelineState:
    """Run the full agent pipeline and return final state."""
    graph = build_agent_graph()

    initial_state = PipelineState(
        user_id=user_id,
        risk_tolerance=risk_tolerance,
        use_mock=use_mock,
    )
    initial_dict = state_to_dict(initial_state)

    logger.info("=" * 60)
    logger.info("STARTING AGENT PIPELINE")
    logger.info("=" * 60)

    t0 = time.perf_counter()
    final_dict = graph.invoke(initial_dict)
    elapsed = time.perf_counter() - t0

    final_state = dict_to_state(final_dict)
    final_state.log("Pipeline", f"Total pipeline time: {elapsed:.3f}s")

    return final_state


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    import argparse

    parser = argparse.ArgumentParser(description="AI Agent Pipeline")
    parser.add_argument("--risk", type=float, default=0.5, help="Risk tolerance 0-1")
    parser.add_argument("--user", type=str, default="valentin")
    args = parser.parse_args()

    state = run_pipeline(user_id=args.user, risk_tolerance=args.risk)

    print("\n" + "=" * 60)
    print("PIPELINE RESULT")
    print("=" * 60)
    print(f"Status : {state.status}")
    print(f"Approved: {state.risk_approved}")
    if state.optimization_result:
        opt = state.optimization_result
        print(f"Solver : {opt.solver_used} ({opt.solver_time_s:.3f}s)")
        print(f"E(r)   : {opt.expected_return:.4f}")
        print(f"Risk σ : {opt.expected_risk:.4f}")
        print("Allocation:")
        for sym, w in opt.weights.items():
            flag = "" if opt.allocation[sym] else " "
            print(f"  [{flag}] {sym:6s}  {w:6.1%}")
    print(f"\nRisk Report: {state.risk_report}")
    print(f"Checks: {json.dumps(state.risk_checks, indent=2)}")
    print(f"\n--- Agent Logs ---")
    for log_entry in state.logs:
        print(f"  {log_entry}")


if __name__ == "__main__":
    main()

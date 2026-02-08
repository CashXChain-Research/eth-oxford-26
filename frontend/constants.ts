// ============================================================
// constants.ts — quantum_vault on-chain addresses & helpers
//
// Usage (Valentin):
//   import { PACKAGE, MODULES, FUNCTIONS, OBJECTS } from './constants';
//
// After deployment, update the placeholder IDs below with
// the real values from `deploy.sh` output or .env.
// ============================================================

declare const process: { env: Record<string, string | undefined> };

// ── Package ─────────────────────────────────────────────────

export const PACKAGE_ID =
  process.env.NEXT_PUBLIC_PACKAGE_ID ??
  '0x0000000000000000000000000000000000000000000000000000000000000000';

// ── Object IDs (filled after deploy.sh) ─────────────────────

export const OBJECTS = {
  /** Shared Portfolio object (created in portfolio::init) */
  PORTFOLIO_ID:
    process.env.NEXT_PUBLIC_PORTFOLIO_ID ??
    '0x0000000000000000000000000000000000000000000000000000000000000000',

  /** AdminCap – owned by Korbinian (created in agent_registry::init) */
  ADMIN_CAP_ID:
    process.env.NEXT_PUBLIC_ADMIN_CAP_ID ??
    '0x0000000000000000000000000000000000000000000000000000000000000000',

  /** AgentCap – owned by Valentin (created via issue_agent_cap) */
  AGENT_CAP_ID:
    process.env.NEXT_PUBLIC_AGENT_CAP_ID ??
    '0x0000000000000000000000000000000000000000000000000000000000000000',

  /** Sui shared Clock */
  SUI_CLOCK: '0x6',
} as const;

// ── Module names ────────────────────────────────────────────

export const MODULES = {
  AGENT_REGISTRY: 'agent_registry',
  PORTFOLIO: 'portfolio',
  AUDIT_TRAIL: 'audit_trail',
  AI_TASK: 'ai_task',
} as const;

// ── Function targets (package::module::function) ────────────

export const FUNCTIONS = {
  // agent_registry
  ISSUE_AGENT_CAP: `${PACKAGE_ID}::${MODULES.AGENT_REGISTRY}::issue_agent_cap`,
  REVOKE_OWN_CAP: `${PACKAGE_ID}::${MODULES.AGENT_REGISTRY}::revoke_own_cap`,

  // portfolio — admin
  DEPOSIT: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::deposit`,
  WITHDRAW: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::withdraw`,
  UPDATE_LIMITS: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::update_limits`,
  FREEZE_AGENT: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::freeze_agent`,
  UNFREEZE_AGENT: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::unfreeze_agent`,
  SET_PAUSED: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::set_paused`,

  // portfolio — agent  ← THE MAIN ENTRY POINTS FOR VALENTIN
  EXECUTE_REBALANCE: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::execute_rebalance`,
  WITHDRAW_FOR_SWAP: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::withdraw_for_swap`,
  DEPOSIT_RETURNS: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::deposit_returns`,
  SWAP_AND_REBALANCE: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::swap_and_rebalance`,

  // portfolio — result objects & mock swap
  EMIT_RESULT: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::emit_result`,
  MOCK_SWAP: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::mock_swap`,

  // ai_task (legacy quantum RNG)
  REGISTER_TASK_AGENT: `${PACKAGE_ID}::${MODULES.AI_TASK}::register_agent`,
  SELECT_WINNER: `${PACKAGE_ID}::${MODULES.AI_TASK}::select_winner`,

  // audit_trail — quantum verification
  LOG_EXECUTION: `${PACKAGE_ID}::${MODULES.AUDIT_TRAIL}::log_execution`,
} as const;

// ── Event types for subscription ────────────────────────────

export const EVENTS = {
  TRADE_EVENT: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::TradeEvent`,
  QUANTUM_TRADE_EVENT: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::QuantumTradeEvent`,
  GUARDRAIL_TRIGGERED: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::GuardrailTriggered`,
  DEPOSITED: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::Deposited`,
  WITHDRAWN: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::Withdrawn`,
  LIMITS_UPDATED: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::LimitsUpdated`,
  PAUSED_CHANGED: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::PausedChanged`,
  AGENT_FROZEN: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::AgentFrozenEvt`,
  AGENT_UNFROZEN: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::AgentUnfrozenEvt`,
  REBALANCE_RESULT: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::RebalanceResultCreated`,
  MOCK_SWAP_EXECUTED: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::MockSwapExecuted`,
  PORTFOLIO_CREATED: `${PACKAGE_ID}::${MODULES.PORTFOLIO}::PortfolioCreated`,
  AGENT_ISSUED: `${PACKAGE_ID}::${MODULES.AGENT_REGISTRY}::AgentIssued`,
  AUDIT_RECEIPT: `${PACKAGE_ID}::${MODULES.AUDIT_TRAIL}::AuditReceiptCreated`,
  QUANTUM_AUDIT: `${PACKAGE_ID}::${MODULES.AUDIT_TRAIL}::QuantumAuditCreated`,
  WINNER_SELECTED: `${PACKAGE_ID}::${MODULES.AI_TASK}::WinnerSelected`,
} as const;

// ── Helpers ─────────────────────────────────────────────────

export function moveCall(module: string, fn: string): string {
  return `${PACKAGE_ID}::${module}::${fn}`;
}

// ── Guardrail defaults (mirror on-chain) ────────────────────

export const GUARDRAIL_DEFAULTS = {
  COOLDOWN_MS: 60_000,            // 60 sec
  DAILY_LIMIT_MIST: 50_000_000_000, // 50 SUI
  MAX_DRAWDOWN_BPS: 1_000,       // 10 %
  BPS_DENOMINATOR: 10_000,
} as const;

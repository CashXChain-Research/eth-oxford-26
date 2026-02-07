/**
 * ptb_builder.ts — Programmable Transaction Block (PTB) builder
 *
 * Valentin: import these helpers to build ready-to-sign transactions.
 * Each function returns a Transaction object.
 * Sign with your keypair, then submit via SuiClient.
 *
 * Usage:
 *   import { buildSwapAndRebalance, buildSetPaused } from './ptb_builder';
 *   const tx = buildSwapAndRebalance({ amountMist: 1_000_000_000, minOutput: 950_000_000 });
 *   const result = await client.signAndExecuteTransaction({ signer: kp, transaction: tx });
 */

import { Transaction } from '@mysten/sui/transactions';
import 'dotenv/config';

// ═══════════════════════════════════════════════════════════
//  ON-CHAIN IDS — filled after deploy.sh
// ═══════════════════════════════════════════════════════════

const PKG          = process.env.PACKAGE_ID!;
const PORTFOLIO_ID = process.env.PORTFOLIO_ID!;
const AGENT_CAP_ID = process.env.AGENT_CAP_ID!;
const ADMIN_CAP_ID = process.env.ADMIN_CAP_ID!;
const SUI_CLOCK    = '0x6';

// ═══════════════════════════════════════════════════════════
//  TYPES
// ═══════════════════════════════════════════════════════════

export interface SwapAndRebalanceParams {
  amountMist: number;
  /** Minimum acceptable output — slippage guardrail. */
  minOutput: number;
  isQuantumOptimized?: boolean;
  /** 0–100 score from quantum RNG. */
  quantumOptimizationScore?: number;
}

export interface PtbSwapParams {
  amountMist: number;
  /** min_output for deposit_returns slippage check. */
  minOutput: number;
  isQuantumOptimized?: boolean;
}

// ═══════════════════════════════════════════════════════════
//  1. swap_and_rebalance  (atomic demo / same-module swap)
//
//  Single Move call: auth → guardrails → slippage → event.
//  Use this for the pitch demo.
// ═══════════════════════════════════════════════════════════

export function buildSwapAndRebalance(params: SwapAndRebalanceParams): Transaction {
  const {
    amountMist,
    minOutput,
    isQuantumOptimized = true,
    quantumOptimizationScore = 0,
  } = params;

  const tx = new Transaction();

  tx.moveCall({
    target: `${PKG}::portfolio::swap_and_rebalance`,
    arguments: [
      tx.object(AGENT_CAP_ID),       // &AgentCap
      tx.object(PORTFOLIO_ID),        // &mut Portfolio
      tx.pure.u64(amountMist),        // amount
      tx.pure.u64(minOutput),         // min_output (slippage)
      tx.pure.bool(isQuantumOptimized),
      tx.pure.u64(quantumOptimizationScore),
      tx.object(SUI_CLOCK),           // &Clock
    ],
  });

  return tx;
}

// ═══════════════════════════════════════════════════════════
//  2. PTB: withdraw_for_swap → DEX → deposit_returns
//
//  Production pattern for real DEX integration.
//  Replace the DEX placeholder with Cetus / Aftermath / DeepBook.
// ═══════════════════════════════════════════════════════════

export function buildDexSwapPtb(params: PtbSwapParams): Transaction {
  const {
    amountMist,
    minOutput,
    isQuantumOptimized = true,
  } = params;

  const tx = new Transaction();

  // Step 1: Withdraw SUI from vault (all guardrails checked here)
  const [coin] = tx.moveCall({
    target: `${PKG}::portfolio::withdraw_for_swap`,
    arguments: [
      tx.object(AGENT_CAP_ID),
      tx.object(PORTFOLIO_ID),
      tx.pure.u64(amountMist),
      tx.pure.bool(isQuantumOptimized),
      tx.object(SUI_CLOCK),
    ],
  });

  // Step 2: DEX swap ── PLACEHOLDER ──
  //
  //   Replace with your DEX of choice, e.g.:
  //
  //   // Cetus
  //   const [outputCoin] = tx.moveCall({
  //     target: `${CETUS_PKG}::router::swap_exact_input`,
  //     arguments: [coin, poolObj, ...],
  //     typeArguments: ['0x2::sui::SUI', TARGET_TOKEN_TYPE],
  //   });
  //
  //   // DeepBook
  //   const [outputCoin] = tx.moveCall({
  //     target: `${DEEPBOOK_PKG}::clob_v2::swap_exact_base_for_quote`,
  //     arguments: [coin, poolObj, ...],
  //   });
  //
  // For demo, round-trip the same coin:
  const outputCoin = coin;

  // Step 3: Deposit swap result back + slippage check
  tx.moveCall({
    target: `${PKG}::portfolio::deposit_returns`,
    arguments: [
      tx.object(PORTFOLIO_ID),
      outputCoin,
      tx.pure.u64(minOutput),       // slippage guardrail
    ],
  });

  return tx;
}

// ═══════════════════════════════════════════════════════════
//  3. execute_rebalance  (demo / dry-run — no fund movement)
// ═══════════════════════════════════════════════════════════

export function buildExecuteRebalance(
  amountMist: number,
  isQuantumOptimized: boolean = true,
): Transaction {
  const tx = new Transaction();

  tx.moveCall({
    target: `${PKG}::portfolio::execute_rebalance`,
    arguments: [
      tx.object(AGENT_CAP_ID),
      tx.object(PORTFOLIO_ID),
      tx.pure.u64(amountMist),
      tx.pure.bool(isQuantumOptimized),
      tx.object(SUI_CLOCK),
    ],
  });

  return tx;
}

// ═══════════════════════════════════════════════════════════
//  4. set_paused  (Admin emergency kill-switch)
// ═══════════════════════════════════════════════════════════

export function buildSetPaused(paused: boolean): Transaction {
  const tx = new Transaction();

  tx.moveCall({
    target: `${PKG}::portfolio::set_paused`,
    arguments: [
      tx.object(ADMIN_CAP_ID),       // &AdminCap
      tx.object(PORTFOLIO_ID),        // &mut Portfolio
      tx.pure.bool(paused),
    ],
  });

  return tx;
}

// ═══════════════════════════════════════════════════════════
//  5. deposit  (Admin fund loading)
// ═══════════════════════════════════════════════════════════

export function buildDeposit(amountMist: number): Transaction {
  const tx = new Transaction();

  const [coin] = tx.splitCoins(tx.gas, [amountMist]);

  tx.moveCall({
    target: `${PKG}::portfolio::deposit`,
    arguments: [
      tx.object(ADMIN_CAP_ID),
      tx.object(PORTFOLIO_ID),
      coin,
    ],
  });

  return tx;
}

// ═══════════════════════════════════════════════════════════
//  6. update_limits  (Admin guardrail tuning)
// ═══════════════════════════════════════════════════════════

export function buildUpdateLimits(
  maxDrawdownBps: number,
  dailyVolumeLimitMist: number,
  cooldownMs: number,
): Transaction {
  const tx = new Transaction();

  tx.moveCall({
    target: `${PKG}::portfolio::update_limits`,
    arguments: [
      tx.object(ADMIN_CAP_ID),
      tx.object(PORTFOLIO_ID),
      tx.pure.u64(maxDrawdownBps),
      tx.pure.u64(dailyVolumeLimitMist),
      tx.pure.u64(cooldownMs),
    ],
  });

  return tx;
}

// ═══════════════════════════════════════════════════════════
//  7. freeze / unfreeze agent
// ═══════════════════════════════════════════════════════════

export function buildFreezeAgent(agentAddress: string): Transaction {
  const tx = new Transaction();

  tx.moveCall({
    target: `${PKG}::portfolio::freeze_agent`,
    arguments: [
      tx.object(ADMIN_CAP_ID),
      tx.object(PORTFOLIO_ID),
      tx.pure.address(agentAddress),
    ],
  });

  return tx;
}

export function buildUnfreezeAgent(agentAddress: string): Transaction {
  const tx = new Transaction();

  tx.moveCall({
    target: `${PKG}::portfolio::unfreeze_agent`,
    arguments: [
      tx.object(ADMIN_CAP_ID),
      tx.object(PORTFOLIO_ID),
      tx.pure.address(agentAddress),
    ],
  });

  return tx;
}

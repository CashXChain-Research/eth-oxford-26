/**
 * agent_executor.ts — Valentins AI Agent Backend
 *
 * Builds and executes Programmable Transaction Blocks (PTBs)
 * against the quantum_vault smart contracts on Sui.
 *
 * Install:
 *   npm install @mysten/sui @mysten/bcs dotenv
 *
 * Usage:
 *   AGENT_PRIVATE_KEY=suiprivkey1... npx ts-node agent_executor.ts
 */

import {
  SuiClient,
  getFullnodeUrl,
} from '@mysten/sui/client';
import { Transaction } from '@mysten/sui/transactions';
import { Ed25519Keypair } from '@mysten/sui/keypairs/ed25519';
import { fromBase64 } from '@mysten/sui/utils';
import 'dotenv/config';

// ═══════════════════════════════════════════════════════════
//  CONFIG
// ═══════════════════════════════════════════════════════════

const NETWORK = (process.env.SUI_NETWORK as 'devnet' | 'testnet' | 'mainnet') ?? 'devnet';
const RPC_URL = process.env.SUI_RPC_URL ?? getFullnodeUrl(NETWORK);

// On-chain IDs — filled after deploy.sh
const PACKAGE_ID    = process.env.PACKAGE_ID!;
const PORTFOLIO_ID  = process.env.PORTFOLIO_ID!;
const AGENT_CAP_ID  = process.env.AGENT_CAP_ID!;
const SUI_CLOCK     = '0x6';

// ═══════════════════════════════════════════════════════════
//  KEYPAIR
// ═══════════════════════════════════════════════════════════

function loadKeypair(): Ed25519Keypair {
  const key = process.env.AGENT_PRIVATE_KEY;
  if (!key) throw new Error('AGENT_PRIVATE_KEY not set');

  // Support both raw hex and Sui-encoded (suiprivkey1...) formats
  if (key.startsWith('suiprivkey')) {
    return Ed25519Keypair.fromSecretKey(key);
  }
  // Raw base64 or hex
  const bytes = key.startsWith('0x')
    ? Uint8Array.from(Buffer.from(key.slice(2), 'hex'))
    : fromBase64(key);
  return Ed25519Keypair.fromSecretKey(bytes);
}

// ═══════════════════════════════════════════════════════════
//  CLIENT
// ═══════════════════════════════════════════════════════════

const client = new SuiClient({ url: RPC_URL });
const keypair = loadKeypair();

console.log(`🔑 Agent address: ${keypair.getPublicKey().toSuiAddress()}`);
console.log(`🌐 Network: ${NETWORK} (${RPC_URL})`);
console.log(`📦 Package: ${PACKAGE_ID}`);

// ═══════════════════════════════════════════════════════════
//  PTB BUILDERS
// ═══════════════════════════════════════════════════════════

/**
 * Demo trade — calls execute_rebalance (no fund movement).
 * Perfect for the pitch: shows guardrails blocking / allowing.
 */
export async function executeRebalance(
  amountMist: number,
  isQuantumOptimized: boolean = true,
): Promise<string> {
  const tx = new Transaction();

  tx.moveCall({
    target: `${PACKAGE_ID}::portfolio::execute_rebalance`,
    arguments: [
      tx.object(AGENT_CAP_ID),
      tx.object(PORTFOLIO_ID),
      tx.pure.u64(amountMist),
      tx.pure.bool(isQuantumOptimized),
      tx.object(SUI_CLOCK),
    ],
  });

  const result = await client.signAndExecuteTransaction({
    signer: keypair,
    transaction: tx,
    options: { showEffects: true, showEvents: true },
  });

  console.log('✅ TX digest:', result.digest);
  if (result.events) {
    for (const ev of result.events) {
      console.log(`  📢 ${ev.type}`, ev.parsedJson);
    }
  }
  return result.digest;
}

/**
 * Production PTB — withdraw → DEX swap → deposit back.
 *
 *   Step 1: withdraw_for_swap  → Coin<SUI>
 *   Step 2: (DEX call — placeholder, e.g. Cetus)
 *   Step 3: deposit_returns    ← Coin<SUI> back to vault
 *
 * All three calls happen in ONE atomic transaction.
 * If any guardrail fails, the ENTIRE PTB reverts.
 */
export async function swapRebalance(
  amountMist: number,
  minOutput: number = 0,
  isQuantumOptimized: boolean = true,
): Promise<string> {
  const tx = new Transaction();

  // Step 1: withdraw SUI from the vault
  const [coin] = tx.moveCall({
    target: `${PACKAGE_ID}::portfolio::withdraw_for_swap`,
    arguments: [
      tx.object(AGENT_CAP_ID),
      tx.object(PORTFOLIO_ID),
      tx.pure.u64(amountMist),
      tx.pure.bool(isQuantumOptimized),
      tx.object(SUI_CLOCK),
    ],
  });

  // Step 2: DEX swap — PLACEHOLDER
  // In production, replace with Cetus / Aftermath / DeepBook call:
  //
  //   const [outputCoin] = tx.moveCall({
  //     target: `${CETUS_PACKAGE}::router::swap_exact_input`,
  //     arguments: [coin, ...],
  //   });
  //
  // For now, we deposit the same coin back (round-trip demo):
  const outputCoin = coin;

  // Step 3: deposit the swap result back into the vault
  tx.moveCall({
    target: `${PACKAGE_ID}::portfolio::deposit_returns`,
    arguments: [
      tx.object(PORTFOLIO_ID),
      outputCoin,
      tx.pure.u64(minOutput),       // slippage guardrail
    ],
  });

  const result = await client.signAndExecuteTransaction({
    signer: keypair,
    transaction: tx,
    options: { showEffects: true, showEvents: true },
  });

  console.log('✅ Swap TX digest:', result.digest);
  if (result.events) {
    for (const ev of result.events) {
      console.log(`  📢 ${ev.type}`, ev.parsedJson);
    }
  }
  return result.digest;
}

/**
 * Dry-run a transaction WITHOUT submitting to the chain.
 * Returns { success: boolean, error?: string }.
 */
export async function dryRun(
  amountMist: number,
  isQuantumOptimized: boolean = true,
): Promise<{ success: boolean; error?: string }> {
  const tx = new Transaction();

  tx.moveCall({
    target: `${PACKAGE_ID}::portfolio::execute_rebalance`,
    arguments: [
      tx.object(AGENT_CAP_ID),
      tx.object(PORTFOLIO_ID),
      tx.pure.u64(amountMist),
      tx.pure.bool(isQuantumOptimized),
      tx.object(SUI_CLOCK),
    ],
  });

  tx.setSender(keypair.getPublicKey().toSuiAddress());

  try {
    const dryResult = await client.dryRunTransactionBlock({
      transactionBlock: await tx.build({ client }),
    });

    const status = dryResult.effects.status;
    if (status.status === 'success') {
      return { success: true };
    }
    return { success: false, error: status.error ?? 'unknown error' };
  } catch (e: any) {
    return { success: false, error: e.message };
  }
}

// ═══════════════════════════════════════════════════════════
//  SWAP AND REBALANCE (atomic demo with slippage + quantum score)
// ═══════════════════════════════════════════════════════════

export async function swapAndRebalance(
  amountMist: number,
  minOutput: number,
  quantumScore: number = 0,
  isQuantumOptimized: boolean = true,
): Promise<string> {
  const tx = new Transaction();

  tx.moveCall({
    target: `${PACKAGE_ID}::portfolio::swap_and_rebalance`,
    arguments: [
      tx.object(AGENT_CAP_ID),
      tx.object(PORTFOLIO_ID),
      tx.pure.u64(amountMist),
      tx.pure.u64(minOutput),
      tx.pure.bool(isQuantumOptimized),
      tx.pure.u64(quantumScore),
      tx.object(SUI_CLOCK),
    ],
  });

  const result = await client.signAndExecuteTransaction({
    signer: keypair,
    transaction: tx,
    options: { showEffects: true, showEvents: true },
  });

  console.log('✅ swap_and_rebalance TX:', result.digest);
  if (result.events) {
    for (const ev of result.events) {
      console.log(`  📢 ${ev.type}`, ev.parsedJson);
    }
  }
  return result.digest;
}

// ═══════════════════════════════════════════════════════════
//  SET PAUSED  (Admin emergency kill-switch)
// ═══════════════════════════════════════════════════════════

const ADMIN_CAP_ID = process.env.ADMIN_CAP_ID!;

export async function setPaused(paused: boolean): Promise<string> {
  const tx = new Transaction();

  tx.moveCall({
    target: `${PACKAGE_ID}::portfolio::set_paused`,
    arguments: [
      tx.object(ADMIN_CAP_ID),
      tx.object(PORTFOLIO_ID),
      tx.pure.bool(paused),
    ],
  });

  const result = await client.signAndExecuteTransaction({
    signer: keypair,
    transaction: tx,
    options: { showEffects: true, showEvents: true },
  });

  console.log(`${paused ? '🛑 PAUSED' : '▶️  RESUMED'} TX: ${result.digest}`);
  return result.digest;
}

// ═══════════════════════════════════════════════════════════
//  EVENT STREAMER  (for Person C / Frontend dashboard)
// ═══════════════════════════════════════════════════════════

export async function streamTradeEvents() {
  console.log('📡 Subscribing to TradeEvent...');

  // Note: WebSocket subscriptions require a WS-enabled RPC
  const unsubscribe = await client.subscribeEvent({
    filter: {
      MoveEventType: `${PACKAGE_ID}::portfolio::TradeEvent`,
    },
    onMessage(event) {
      const d = event.parsedJson as any;
      console.log(`\n🔔 Trade #${d.trade_id}`);
      console.log(`   Agent:    ${d.agent_address}`);
      console.log(`   Amount:   ${d.input_amount} MIST`);
      console.log(`   Balance:  ${d.balance_before} → ${d.balance_after}`);
      console.log(`   Quantum:  ${d.is_quantum_optimized ? '⚛️  YES' : '❌ NO'}`);
    },
  });

  // Keep alive — Ctrl+C to stop
  process.on('SIGINT', async () => {
    await unsubscribe();
    process.exit(0);
  });
}

// ═══════════════════════════════════════════════════════════
//  CLI
// ═══════════════════════════════════════════════════════════

async function main() {
  const cmd = process.argv[2] ?? 'demo';
  const amount = parseInt(process.argv[3] ?? '1000000000', 10); // default 1 SUI

  switch (cmd) {
    case 'demo':
      console.log(`\n🚀 Demo rebalance: ${amount} MIST`);
      await executeRebalance(amount, true);
      break;

    case 'swap':
      console.log(`\n🔄 Swap rebalance: ${amount} MIST`);
      await swapRebalance(amount, 0, true);
      break;

    case 'quantum':
      console.log(`\n⚛️  Quantum swap_and_rebalance: ${amount} MIST`);
      const minOut = parseInt(process.argv[4] ?? String(Math.floor(amount * 0.9)), 10);
      const qScore = parseInt(process.argv[5] ?? '85', 10);
      await swapAndRebalance(amount, minOut, qScore, true);
      break;

    case 'pause':
      console.log('\n🛑 Pausing portfolio...');
      await setPaused(true);
      break;

    case 'resume':
      console.log('\n▶️  Resuming portfolio...');
      await setPaused(false);
      break;

    case 'dryrun':
      console.log(`\n🧪 Dry-run: ${amount} MIST`);
      const result = await dryRun(amount, true);
      if (result.success) {
        console.log('✅ Dry-run PASSED — guardrails OK');
      } else {
        console.log(`🛑 Dry-run BLOCKED: ${result.error}`);
      }
      break;

    case 'killswitch':
      // "Fat Finger" test: try to trade 100% of portfolio
      console.log('\n💀 KILL-SWITCH TEST: attempting 100% portfolio drain...');
      const portfolio = await client.getObject({
        id: PORTFOLIO_ID,
        options: { showContent: true },
      });
      const fields = (portfolio.data?.content as any)?.fields;
      const fullBalance = parseInt(fields?.balance ?? '999999999999', 10);
      console.log(`   Portfolio balance: ${fullBalance} MIST`);
      console.log(`   Attempting trade:  ${fullBalance} MIST (100%)`);

      const ks = await dryRun(fullBalance, false);
      if (ks.success) {
        console.log('⚠️  Trade would PASS — check your guardrails!');
      } else {
        console.log(`🛡️  BLOCKED by guardrails: ${ks.error}`);
        console.log('✅ Kill-switch working! Portfolio is safe.');
      }
      break;

    case 'stream':
      await streamTradeEvents();
      break;

    default:
      console.log('Usage: npx ts-node agent_executor.ts <demo|swap|quantum|dryrun|killswitch|pause|resume|stream> [amount_mist] [min_output] [quantum_score]');
  }
}

main().catch(console.error);

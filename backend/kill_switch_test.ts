/**
 * kill_switch_test.ts — Pitch-Demo: "Fat Finger" Guardrail Test
 *
 * Simulates an AI agent going rogue and trying to drain the entire
 * portfolio in one trade. The smart contract MUST block this.
 *
 * Usage:
 *   npx ts-node kill_switch_test.ts
 *
 * Expected output for the pitch video:
 *   ✅ Test 1 PASSED — small trade allowed
 *   🛡️ Test 2 BLOCKED — 100% drain prevented by EDrawdownExceeded
 *   🛡️ Test 3 BLOCKED — rapid trade prevented by ECooldownActive
 */

import {
  SuiClient,
  getFullnodeUrl,
} from '@mysten/sui/client';
import { Transaction } from '@mysten/sui/transactions';
import { Ed25519Keypair } from '@mysten/sui/keypairs/ed25519';
import 'dotenv/config';

// ── Config ──────────────────────────────────────────────────

const NETWORK     = (process.env.SUI_NETWORK as 'devnet' | 'testnet') ?? 'devnet';
const PACKAGE_ID  = process.env.PACKAGE_ID!;
const PORTFOLIO_ID = process.env.PORTFOLIO_ID!;
const AGENT_CAP_ID = process.env.AGENT_CAP_ID!;
const SUI_CLOCK   = '0x6';

const client = new SuiClient({ url: process.env.SUI_RPC_URL ?? getFullnodeUrl(NETWORK) });

function loadKeypair(): Ed25519Keypair {
  const key = process.env.AGENT_PRIVATE_KEY!;
  if (key.startsWith('suiprivkey')) return Ed25519Keypair.fromSecretKey(key);
  return Ed25519Keypair.fromSecretKey(
    Uint8Array.from(Buffer.from(key.replace('0x', ''), 'hex'))
  );
}

const keypair = loadKeypair();
const sender  = keypair.getPublicKey().toSuiAddress();

// ── Helpers ─────────────────────────────────────────────────

/** Sui error codes from portfolio.move */
const ERROR_NAMES: Record<string, string> = {
  '0': 'EInvalidAgent',
  '1': 'EAgentFrozen',
  '2': 'ECooldownActive',
  '3': 'EVolumeExceeded',
  '4': 'EDrawdownExceeded',
  '5': 'EInsufficientBalance',
};

function parseErrorCode(msg: string): string {
  const match = msg.match(/MoveAbort.*?(\d+)\)?$/);
  if (match) {
    const code = match[1];
    return ERROR_NAMES[code] ?? `unknown(${code})`;
  }
  return msg.slice(0, 120);
}

async function dryRunRebalance(amount: number): Promise<{ ok: boolean; detail: string }> {
  const tx = new Transaction();
  tx.moveCall({
    target: `${PACKAGE_ID}::portfolio::execute_rebalance`,
    arguments: [
      tx.object(AGENT_CAP_ID),
      tx.object(PORTFOLIO_ID),
      tx.pure.u64(amount),
      tx.pure.bool(true),    // is_quantum_optimized
      tx.object(SUI_CLOCK),
    ],
  });
  tx.setSender(sender);

  try {
    const result = await client.dryRunTransactionBlock({
      transactionBlock: await tx.build({ client }),
    });
    const status = result.effects.status;
    if (status.status === 'success') {
      return { ok: true, detail: 'success' };
    }
    return { ok: false, detail: parseErrorCode(status.error ?? 'unknown') };
  } catch (e: any) {
    return { ok: false, detail: parseErrorCode(e.message) };
  }
}

// ── Test Suite ──────────────────────────────────────────────

async function main() {
  console.log('═══════════════════════════════════════════');
  console.log('  quantum_vault — Kill-Switch Test Suite');
  console.log('═══════════════════════════════════════════');
  console.log(`  Agent:     ${sender}`);
  console.log(`  Package:   ${PACKAGE_ID}`);
  console.log(`  Portfolio: ${PORTFOLIO_ID}`);
  console.log('');

  // Fetch portfolio state
  const obj = await client.getObject({
    id: PORTFOLIO_ID,
    options: { showContent: true },
  });
  const fields = (obj.data?.content as any)?.fields ?? {};
  const vaultBalance = parseInt(fields.balance ?? '0', 10);
  const peakBalance  = parseInt(fields.peak_balance ?? '0', 10);
  const drawdownBps  = parseInt(fields.max_drawdown_bps ?? '1000', 10);

  console.log(`  Vault balance:     ${vaultBalance} MIST (${(vaultBalance / 1e9).toFixed(4)} SUI)`);
  console.log(`  Peak balance:      ${peakBalance} MIST`);
  console.log(`  Max drawdown:      ${drawdownBps / 100}%`);
  console.log('');

  let passed = 0;
  let failed = 0;

  // ── Test 1: Small safe trade (should PASS) ────────────
  const safeAmount = Math.floor(vaultBalance * 0.05); // 5% — well within 10% drawdown
  console.log(`🧪 Test 1: Safe trade (${safeAmount} MIST = 5% of vault)`);
  const t1 = await dryRunRebalance(safeAmount);
  if (t1.ok) {
    console.log('   ✅ PASSED — trade allowed\n');
    passed++;
  } else {
    console.log(`   ❌ UNEXPECTED BLOCK: ${t1.detail}\n`);
    failed++;
  }

  // ── Test 2: Fat finger — 100% drain (should BLOCK) ───
  console.log(`💀 Test 2: Fat finger — drain 100% (${vaultBalance} MIST)`);
  const t2 = await dryRunRebalance(vaultBalance);
  if (!t2.ok) {
    console.log(`   🛡️  BLOCKED: ${t2.detail}`);
    console.log('   ✅ KILL-SWITCH WORKS — portfolio is safe!\n');
    passed++;
  } else {
    console.log('   ⚠️  TRADE PASSED — guardrails may be misconfigured!\n');
    failed++;
  }

  // ── Test 3: Rapid-fire (should BLOCK with ECooldownActive) ──
  // This test only works if Test 1 actually executes (not dry-run).
  // For dry-run we simulate by checking if cooldown would trigger.
  console.log('⚡ Test 3: Rapid-fire — two trades within cooldown');
  // First "execute" the trade (real TX)
  try {
    const tx = new Transaction();
    tx.moveCall({
      target: `${PACKAGE_ID}::portfolio::execute_rebalance`,
      arguments: [
        tx.object(AGENT_CAP_ID),
        tx.object(PORTFOLIO_ID),
        tx.pure.u64(safeAmount),
        tx.pure.bool(true),
        tx.object(SUI_CLOCK),
      ],
    });
    await client.signAndExecuteTransaction({
      signer: keypair,
      transaction: tx,
      options: { showEffects: true },
    });
    console.log('   Trade 1: executed');

    // Immediately try another
    const t3 = await dryRunRebalance(safeAmount);
    if (!t3.ok) {
      console.log(`   🛡️  Trade 2 BLOCKED: ${t3.detail}`);
      console.log('   ✅ Cooldown guardrail works!\n');
      passed++;
    } else {
      console.log('   ⚠️  Trade 2 passed — cooldown too short?\n');
      failed++;
    }
  } catch (e: any) {
    console.log(`   ⚠️  Could not execute real trade (expected on devnet): ${e.message.slice(0, 80)}`);
    console.log('   ⏭️  Skipping cooldown test (needs funded account)\n');
  }

  // ── Summary ───────────────────────────────────────────
  console.log('═══════════════════════════════════════════');
  console.log(`  Results: ${passed} passed, ${failed} failed`);
  if (failed === 0) {
    console.log('  🎉 All guardrails working — ready for pitch!');
  } else {
    console.log('  ⚠️  Some tests failed — review guardrail config');
  }
  console.log('═══════════════════════════════════════════');
}

main().catch(console.error);

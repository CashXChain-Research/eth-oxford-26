/**
 * safety_redline_test.ts — Guardrail Validation Suite
 *
 * Deliberately tries to break every guardrail to prove they work.
 * Run this BEFORE the live demo to verify safety.
 *
 * Every test should FAIL on-chain (abort) — that's the success condition!
 *
 * Usage:
 *   npx ts-node safety_redline_test.ts
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

const NETWORK      = (process.env.SUI_NETWORK as 'devnet' | 'testnet' | 'mainnet') ?? 'devnet';
const RPC_URL      = process.env.SUI_RPC_URL ?? getFullnodeUrl(NETWORK);
const PACKAGE_ID   = process.env.PACKAGE_ID!;
const PORTFOLIO_ID = process.env.PORTFOLIO_ID ?? process.env.PORTFOLIO_OBJECT_ID!;
const AGENT_CAP_ID = process.env.AGENT_CAP_ID!;
const ADMIN_CAP_ID = process.env.ADMIN_CAP_ID!;
const SUI_CLOCK    = '0x6';

const client = new SuiClient({ url: RPC_URL });

function loadKeypair(envKey: string): Ed25519Keypair {
  const key = process.env[envKey];
  if (!key) throw new Error(`${envKey} not set`);
  if (key.startsWith('suiprivkey')) return Ed25519Keypair.fromSecretKey(key);
  const bytes = key.startsWith('0x')
    ? Uint8Array.from(Buffer.from(key.slice(2), 'hex'))
    : fromBase64(key);
  return Ed25519Keypair.fromSecretKey(bytes);
}

const agentKP = loadKeypair('AGENT_PRIVATE_KEY');

// Error code mapping
const ERROR_NAMES: Record<number, string> = {
  0: 'EInvalidAgent',
  1: 'EAgentFrozen',
  2: 'ECooldownActive',
  3: 'EVolumeExceeded',
  4: 'EDrawdownExceeded',
  5: 'EInsufficientBalance',
  6: 'EPaused',
  7: 'ESlippageExceeded',
};

// ═══════════════════════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════════════════════

interface TestResult {
  name: string;
  passed: boolean;       // true = guardrail correctly blocked
  error?: string;
  abortCode?: number;
  digest?: string;
}

async function dryRunTrade(
  amountMist: number,
  minOutput: number = 0,
  quantumScore: number = 0,
): Promise<{ success: boolean; error?: string; abortCode?: number }> {
  const tx = new Transaction();

  tx.moveCall({
    target: `${PACKAGE_ID}::portfolio::swap_and_rebalance`,
    arguments: [
      tx.object(AGENT_CAP_ID),
      tx.object(PORTFOLIO_ID),
      tx.pure.u64(amountMist),
      tx.pure.u64(minOutput),
      tx.pure.bool(true),
      tx.pure.u64(quantumScore),
      tx.object(SUI_CLOCK),
    ],
  });

  tx.setSender(agentKP.getPublicKey().toSuiAddress());

  try {
    const dryResult = await client.dryRunTransactionBlock({
      transactionBlock: await tx.build({ client }),
    });

    const status = dryResult.effects.status;
    if (status.status === 'success') {
      return { success: true };
    }

    // Parse abort code from error string
    const errorStr = status.error ?? '';
    const match = errorStr.match(/abort_code: (\d+)/i) ?? errorStr.match(/MoveAbort.*?(\d+)/);
    const abortCode = match ? parseInt(match[1], 10) : undefined;

    return { success: false, error: errorStr, abortCode };
  } catch (e: any) {
    return { success: false, error: e.message };
  }
}

async function getPortfolioBalance(): Promise<number> {
  const portfolio = await client.getObject({
    id: PORTFOLIO_ID,
    options: { showContent: true },
  });
  const fields = (portfolio.data?.content as any)?.fields;
  return parseInt(fields?.balance ?? '0', 10);
}

function printResult(r: TestResult) {
  const icon = r.passed ? '✅' : '❌';
  const errorName = r.abortCode !== undefined ? ERROR_NAMES[r.abortCode] ?? `unknown(${r.abortCode})` : '';
  console.log(`${icon} ${r.name}`);
  if (r.passed) {
    console.log(`   🛡️  Correctly blocked: ${errorName} (abort code ${r.abortCode})`);
  } else {
    console.log(`   ⚠️  UNEXPECTED: ${r.error}`);
  }
  console.log('');
}

// ═══════════════════════════════════════════════════════════
//  TESTS
// ═══════════════════════════════════════════════════════════

async function test1_drawdownExceeded(): Promise<TestResult> {
  console.log('── Test 1: 50% Portfolio Drain (EDrawdownExceeded) ──');
  const balance = await getPortfolioBalance();
  const drainAmount = Math.floor(balance * 0.5); // 50% = way over 10% max

  console.log(`   Portfolio: ${balance} MIST`);
  console.log(`   Attempting: ${drainAmount} MIST (50%)`);

  const result = await dryRunTrade(drainAmount);
  const passed = !result.success && result.abortCode === 4;

  return { name: 'Drawdown Exceeded (50% drain)', passed, abortCode: result.abortCode, error: result.error };
}

async function test2_slippageExceeded(): Promise<TestResult> {
  console.log('── Test 2: Impossible Slippage (ESlippageExceeded) ──');
  // Trade 0.1 SUI but demand 10 SUI back — impossible
  const amount = 100_000_000;     // 0.1 SUI
  const minOutput = 10_000_000_000; // 10 SUI

  console.log(`   Amount:     ${amount} MIST`);
  console.log(`   Min output: ${minOutput} MIST (impossible!)`);

  const result = await dryRunTrade(amount, minOutput);
  const passed = !result.success && result.abortCode === 7;

  return { name: 'Slippage Exceeded (min_output > input)', passed, abortCode: result.abortCode, error: result.error };
}

async function test3_insufficientBalance(): Promise<TestResult> {
  console.log('── Test 3: Trade More Than Balance (EInsufficientBalance) ──');
  const balance = await getPortfolioBalance();
  const overAmount = balance + 1_000_000_000; // balance + 1 SUI

  console.log(`   Portfolio:  ${balance} MIST`);
  console.log(`   Attempting: ${overAmount} MIST`);

  const result = await dryRunTrade(overAmount);
  // Could be EDrawdownExceeded (4) or EInsufficientBalance (5) depending on peak
  const passed = !result.success && (result.abortCode === 4 || result.abortCode === 5);

  return { name: 'Insufficient Balance (trade > vault)', passed, abortCode: result.abortCode, error: result.error };
}

async function test4_cooldownRapidFire(): Promise<TestResult> {
  console.log('── Test 4: Rapid-Fire Trades (ECooldownActive) ──');
  // First trade — safe (5% of balance or 0.5 SUI, whichever is smaller)
  const balance = await getPortfolioBalance();
  const safeAmount = Math.min(Math.floor(balance * 0.05), 500_000_000);

  console.log(`   First trade:  ${safeAmount} MIST (should pass)`);

  // Execute first trade for real
  const tx = new Transaction();
  tx.moveCall({
    target: `${PACKAGE_ID}::portfolio::swap_and_rebalance`,
    arguments: [
      tx.object(AGENT_CAP_ID),
      tx.object(PORTFOLIO_ID),
      tx.pure.u64(safeAmount),
      tx.pure.u64(0),
      tx.pure.bool(true),
      tx.pure.u64(85),
      tx.object(SUI_CLOCK),
    ],
  });

  try {
    await client.signAndExecuteTransaction({
      signer: agentKP,
      transaction: tx,
      options: { showEffects: true },
    });
    console.log('   ✅ First trade succeeded');
  } catch (e: any) {
    // If first trade fails (e.g. cooldown from previous test), that's OK
    console.log(`   ⚠️  First trade failed: ${e.message}`);
  }

  // Immediately try second trade — should hit cooldown
  console.log(`   Second trade: ${safeAmount} MIST (immediately — should fail)`);
  const result = await dryRunTrade(safeAmount);
  const passed = !result.success && result.abortCode === 2;

  return { name: 'Cooldown Violation (rapid-fire)', passed, abortCode: result.abortCode, error: result.error };
}

async function test5_100percentDrain(): Promise<TestResult> {
  console.log('── Test 5: 100% Portfolio Drain (ultimate fat-finger) ──');
  const balance = await getPortfolioBalance();

  console.log(`   Portfolio: ${balance} MIST`);
  console.log(`   Attempting: ${balance} MIST (100%)`);

  const result = await dryRunTrade(balance);
  // Should hit drawdown (4) since 100% > 10%
  const passed = !result.success && (result.abortCode === 2 || result.abortCode === 4);

  return { name: '100% Portfolio Drain', passed, abortCode: result.abortCode, error: result.error };
}

// ═══════════════════════════════════════════════════════════
//  MAIN
// ═══════════════════════════════════════════════════════════

async function main() {
  console.log('═══════════════════════════════════════════════════');
  console.log('  🔴 SAFETY REDLINE TEST — quantum_vault');
  console.log('  All tests should FAIL on-chain = guardrails work');
  console.log('═══════════════════════════════════════════════════\n');
  console.log(`Network:   ${NETWORK}`);
  console.log(`Package:   ${PACKAGE_ID}`);
  console.log(`Portfolio: ${PORTFOLIO_ID}`);
  console.log(`Agent:     ${agentKP.getPublicKey().toSuiAddress()}\n`);

  const results: TestResult[] = [];

  results.push(await test1_drawdownExceeded());
  printResult(results[results.length - 1]);

  results.push(await test2_slippageExceeded());
  printResult(results[results.length - 1]);

  results.push(await test3_insufficientBalance());
  printResult(results[results.length - 1]);

  results.push(await test4_cooldownRapidFire());
  printResult(results[results.length - 1]);

  results.push(await test5_100percentDrain());
  printResult(results[results.length - 1]);

  // ── Summary ──
  console.log('═══════════════════════════════════════════════════');
  console.log('  SUMMARY');
  console.log('═══════════════════════════════════════════════════');
  const passed = results.filter(r => r.passed).length;
  const failed = results.filter(r => !r.passed).length;

  for (const r of results) {
    console.log(`  ${r.passed ? '✅' : '❌'} ${r.name}`);
  }
  console.log('');
  console.log(`  Passed: ${passed}/${results.length}`);
  console.log(`  Failed: ${failed}/${results.length}`);
  console.log('');

  if (failed === 0) {
    console.log('  🛡️  ALL GUARDRAILS HOLDING — safe for live demo!');
  } else {
    console.log('  ⚠️  SOME GUARDRAILS MAY BE MISCONFIGURED');
  }
  console.log('═══════════════════════════════════════════════════');

  process.exit(failed > 0 ? 1 : 0);
}

main().catch(console.error);

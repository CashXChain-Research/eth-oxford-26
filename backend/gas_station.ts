/**
 * gas_station.ts — Gas Balance Monitor for Valentin
 *
 * Checks agent and admin SUI balances and warns when gas is low.
 * Can run standalone or be imported into the relayer.
 *
 * Usage:
 *   npx ts-node gas_station.ts              # one-shot check
 *   npx ts-node gas_station.ts --watch      # continuous monitoring
 *   # or: npm run gas
 */

import {
  SuiClient,
  getFullnodeUrl,
} from '@mysten/sui/client';
import { Ed25519Keypair } from '@mysten/sui/keypairs/ed25519';
import { fromBase64 } from '@mysten/sui/utils';
import 'dotenv/config';

// ═══════════════════════════════════════════════════════════
//  CONFIG
// ═══════════════════════════════════════════════════════════

const NETWORK = (process.env.SUI_NETWORK as 'devnet' | 'testnet' | 'mainnet') ?? 'devnet';
const RPC_URL = process.env.SUI_RPC_URL ?? getFullnodeUrl(NETWORK);
const client  = new SuiClient({ url: RPC_URL });

/** Minimum gas balance before we fire a warning (in MIST) */
const MIN_GAS_MIST       = BigInt(process.env.MIN_GAS_MIST ?? '500000000');     // 0.5 SUI
const CRITICAL_GAS_MIST  = BigInt(process.env.CRITICAL_GAS_MIST ?? '100000000'); // 0.1 SUI
const FAUCET_URLS: Record<string, string> = {
  devnet:  'https://faucet.devnet.sui.io/gas',
  testnet: 'https://faucet.testnet.sui.io/v1/gas',
};

// ═══════════════════════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════════════════════

function loadAddress(envKey: string): string | null {
  const key = process.env[envKey];
  if (!key) return null;

  try {
    if (key.startsWith('suiprivkey')) {
      return Ed25519Keypair.fromSecretKey(key).getPublicKey().toSuiAddress();
    }
    const bytes = key.startsWith('0x')
      ? Uint8Array.from(Buffer.from(key.slice(2), 'hex'))
      : fromBase64(key);
    return Ed25519Keypair.fromSecretKey(bytes).getPublicKey().toSuiAddress();
  } catch {
    return null;
  }
}

export interface GasStatus {
  address: string;
  role: string;
  balanceMist: bigint;
  balanceSui: string;
  level: 'ok' | 'low' | 'critical' | 'empty';
  message: string;
}

async function checkBalance(address: string, role: string): Promise<GasStatus> {
  const coins = await client.getCoins({
    owner: address,
    coinType: '0x2::sui::SUI',
  });

  const total = coins.data.reduce(
    (acc: bigint, c: any) => acc + BigInt(c.balance),
    BigInt(0),
  );

  let level: GasStatus['level'];
  let message: string;

  if (total === BigInt(0)) {
    level = 'empty';
    message = `🚨 ${role} hat KEIN Gas! Sofort Faucet nutzen.`;
  } else if (total < CRITICAL_GAS_MIST) {
    level = 'critical';
    message = `🔴 ${role} Gas KRITISCH: ${formatSui(total)} SUI — Trades werden bald fehlschlagen!`;
  } else if (total < MIN_GAS_MIST) {
    level = 'low';
    message = `🟡 ${role} Gas niedrig: ${formatSui(total)} SUI — bald auffüllen.`;
  } else {
    level = 'ok';
    message = `🟢 ${role} Gas OK: ${formatSui(total)} SUI`;
  }

  return {
    address,
    role,
    balanceMist: total,
    balanceSui: formatSui(total),
    level,
    message,
  };
}

function formatSui(mist: bigint): string {
  return (Number(mist) / 1e9).toFixed(4);
}

// ═══════════════════════════════════════════════════════════
//  PUBLIC API (importable by relayer)
// ═══════════════════════════════════════════════════════════

export async function checkAllGas(): Promise<GasStatus[]> {
  const results: GasStatus[] = [];

  const agentAddr = loadAddress('AGENT_PRIVATE_KEY');
  const adminAddr = loadAddress('ADMIN_PRIVATE_KEY');

  if (agentAddr) {
    results.push(await checkBalance(agentAddr, 'Agent (Valentin)'));
  }
  if (adminAddr) {
    results.push(await checkBalance(adminAddr, 'Admin (Korbinian)'));
  }

  return results;
}

export async function isGasSufficient(): Promise<boolean> {
  const statuses = await checkAllGas();
  return statuses.every((s) => s.level === 'ok' || s.level === 'low');
}

// ═══════════════════════════════════════════════════════════
//  AUTO-FAUCET (devnet/testnet only)
// ═══════════════════════════════════════════════════════════

async function requestFaucet(address: string): Promise<boolean> {
  const url = FAUCET_URLS[NETWORK];
  if (!url) {
    console.log(`   ⚠️  Kein Faucet für ${NETWORK} verfügbar.`);
    return false;
  }

  try {
    console.log(`   💧 Faucet-Anfrage für ${address}...`);
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        FixedAmountRequest: { recipient: address },
      }),
    });

    if (resp.ok) {
      console.log(`   ✅ Faucet erfolgreich!`);
      return true;
    } else {
      console.log(`   ❌ Faucet-Fehler: ${resp.status} ${resp.statusText}`);
      return false;
    }
  } catch (e: any) {
    console.log(`   ❌ Faucet-Fehler: ${e.message}`);
    return false;
  }
}

// ═══════════════════════════════════════════════════════════
//  CLI
// ═══════════════════════════════════════════════════════════

async function printStatus() {
  console.log('\n═══════════════════════════════════════════════════');
  console.log('  ⛽ Gas Station — Balance Monitor');
  console.log('═══════════════════════════════════════════════════');
  console.log(`  Network:  ${NETWORK}`);
  console.log(`  Min Gas:  ${formatSui(MIN_GAS_MIST)} SUI`);
  console.log(`  Critical: ${formatSui(CRITICAL_GAS_MIST)} SUI\n`);

  const statuses = await checkAllGas();

  if (statuses.length === 0) {
    console.log('  ⚠️  Keine Keys in .env gefunden (AGENT_PRIVATE_KEY / ADMIN_PRIVATE_KEY)');
    return statuses;
  }

  for (const s of statuses) {
    console.log(`  ${s.message}`);
    console.log(`     Address: ${s.address}`);
    console.log(`     Balance: ${s.balanceMist.toString()} MIST\n`);

    // Auto-faucet if critical/empty on devnet/testnet
    if ((s.level === 'critical' || s.level === 'empty') && FAUCET_URLS[NETWORK]) {
      await requestFaucet(s.address);
    }
  }

  return statuses;
}

async function main() {
  const watchMode = process.argv.includes('--watch');

  await printStatus();

  if (watchMode) {
    const interval = parseInt(process.env.GAS_CHECK_INTERVAL ?? '30000', 10);
    console.log(`\n  👀 Watch-Modus: Prüfe alle ${interval / 1000}s ...\n`);

    setInterval(async () => {
      const statuses = await checkAllGas();
      for (const s of statuses) {
        if (s.level !== 'ok') {
          console.log(`  ${s.message}`);
          if ((s.level === 'critical' || s.level === 'empty') && FAUCET_URLS[NETWORK]) {
            await requestFaucet(s.address);
          }
        }
      }
    }, interval);
  }
}

main().catch(console.error);

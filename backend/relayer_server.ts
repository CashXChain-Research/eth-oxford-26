/**
 * relayer_server.ts — Express Relayer Service for Valentin
 *
 * Accepts optimized portfolio weights from Valentin's Python/Rust
 * backend via REST, builds PTBs, signs with AgentCap key, and
 * submits to Sui testnet.
 *
 * Endpoints:
 *   POST /api/trade       — Execute a quantum-optimized trade
 *   POST /api/audit       — Log a quantum proof hash on-chain
 *   POST /api/pause       — Emergency kill-switch (admin only)
 *   GET  /api/status      — Portfolio status + gas balance
 *   GET  /api/health      — Health check
 *
 * Start:
 *   npx ts-node relayer_server.ts
 *   # or: npm run relayer:server
 */

// eslint-disable-next-line @typescript-eslint/no-require-imports
const express = require('express');
import { Request, Response } from 'express';
import {
  SuiClient,
  getFullnodeUrl,
} from '@mysten/sui/client';
import { Transaction } from '@mysten/sui/transactions';
import { Ed25519Keypair } from '@mysten/sui/keypairs/ed25519';
import { fromBase64 } from '@mysten/sui/utils';
import * as crypto from 'crypto';
import 'dotenv/config';
import { parseAbortError, errorResponseBody, logError } from './error_map';

// ═══════════════════════════════════════════════════════════
//  CONFIG
// ═══════════════════════════════════════════════════════════

const PORT         = parseInt(process.env.RELAYER_PORT ?? '3001', 10);
const NETWORK      = (process.env.SUI_NETWORK as 'devnet' | 'testnet' | 'mainnet') ?? 'devnet';
const RPC_URL      = process.env.SUI_RPC_URL ?? getFullnodeUrl(NETWORK);

const PACKAGE_ID   = process.env.PACKAGE_ID!;
const PORTFOLIO_ID = process.env.PORTFOLIO_ID ?? process.env.PORTFOLIO_OBJECT_ID!;
const AGENT_CAP_ID = process.env.AGENT_CAP_ID!;
const ADMIN_CAP_ID = process.env.ADMIN_CAP_ID!;
const SUI_CLOCK    = '0x6';

// ═══════════════════════════════════════════════════════════
//  KEYPAIR
// ═══════════════════════════════════════════════════════════

function loadKeypair(envKey: string): Ed25519Keypair {
  const key = process.env[envKey];
  if (!key) throw new Error(`${envKey} not set in .env`);

  if (key.startsWith('suiprivkey')) {
    return Ed25519Keypair.fromSecretKey(key);
  }
  const bytes = key.startsWith('0x')
    ? Uint8Array.from(Buffer.from(key.slice(2), 'hex'))
    : fromBase64(key);
  return Ed25519Keypair.fromSecretKey(bytes);
}

const agentKeypair = loadKeypair('AGENT_PRIVATE_KEY');
const client       = new SuiClient({ url: RPC_URL });

// Try to load admin keypair (only Korbinian has this)
let adminKeypair: Ed25519Keypair | null = null;
try {
  adminKeypair = loadKeypair('ADMIN_PRIVATE_KEY');
} catch {
  console.log('⚠️  ADMIN_PRIVATE_KEY not set — pause endpoint disabled');
}

// ═══════════════════════════════════════════════════════════
//  EXPRESS APP
// ═══════════════════════════════════════════════════════════

const app = express();
app.use(express.json());

// ── Health check ────────────────────────────────────────────

app.get('/api/health', (_req: Request, res: Response) => {
  res.json({
    status: 'ok',
    network: NETWORK,
    rpc: RPC_URL,
    package: PACKAGE_ID,
    agent: agentKeypair.getPublicKey().toSuiAddress(),
    timestamp: new Date().toISOString(),
  });
});

// ── Portfolio status ────────────────────────────────────────

app.get('/api/status', async (_req: Request, res: Response) => {
  try {
    const portfolio = await client.getObject({
      id: PORTFOLIO_ID,
      options: { showContent: true },
    });

    const fields = (portfolio.data?.content as any)?.fields ?? {};

    // Agent gas balance
    const agentAddr = agentKeypair.getPublicKey().toSuiAddress();
    const coins = await client.getCoins({ owner: agentAddr, coinType: '0x2::sui::SUI' });
    const gasBalance = coins.data.reduce(
      (acc: bigint, c: any) => acc + BigInt(c.balance), BigInt(0),
    );

    res.json({
      portfolio: {
        id: PORTFOLIO_ID,
        balance: fields.balance,
        peak_balance: fields.peak_balance,
        trade_count: fields.trade_count,
        paused: fields.paused,
        max_drawdown_bps: fields.max_drawdown_bps,
        daily_volume_limit: fields.daily_volume_limit,
        cooldown_ms: fields.cooldown_ms,
        total_traded_today: fields.total_traded_today,
      },
      agent: {
        address: agentAddr,
        gas_balance_mist: gasBalance.toString(),
        gas_balance_sui: (Number(gasBalance) / 1e9).toFixed(4),
      },
    });
  } catch (e: any) {
    res.status(500).json({ error: e.message });
  }
});

// ── Execute trade ───────────────────────────────────────────

interface TradeRequest {
  /** Amount in MIST (1 SUI = 1_000_000_000 MIST) */
  amount: number;
  /** Minimum acceptable output — slippage protection */
  min_output: number;
  /** 0–100 quantum optimization score */
  quantum_score?: number;
  /** true if based on quantum RNG */
  is_quantum_optimized?: boolean;
  /** Optional: raw QUBO solution data for proof hashing */
  qubo_solution_data?: string;
}

app.post('/api/trade', async (req: Request, res: Response) => {
  try {
    const body = req.body as TradeRequest;

    if (!body.amount || body.amount <= 0) {
      res.status(400).json({ error: 'amount must be > 0' });
      return;
    }
    if (body.min_output === undefined || body.min_output < 0) {
      res.status(400).json({ error: 'min_output is required and must be >= 0' });
      return;
    }

    const amount            = body.amount;
    const minOutput         = body.min_output;
    const quantumScore      = body.quantum_score ?? 0;
    const isQuantumOptimized = body.is_quantum_optimized ?? true;

    console.log(`\n📥 Trade request: ${amount} MIST, min_output=${minOutput}, q_score=${quantumScore}`);

    // ── Build PTB ──
    const tx = new Transaction();

    tx.moveCall({
      target: `${PACKAGE_ID}::portfolio::swap_and_rebalance`,
      arguments: [
        tx.object(AGENT_CAP_ID),
        tx.object(PORTFOLIO_ID),
        tx.pure.u64(amount),
        tx.pure.u64(minOutput),
        tx.pure.bool(isQuantumOptimized),
        tx.pure.u64(quantumScore),
        tx.object(SUI_CLOCK),
      ],
    });

    // If QUBO solution data provided, also log a quantum audit receipt
    if (body.qubo_solution_data) {
      const proofHash = crypto
        .createHash('sha256')
        .update(body.qubo_solution_data)
        .digest();

      tx.moveCall({
        target: `${PACKAGE_ID}::audit_trail::log_execution`,
        arguments: [
          tx.object(AGENT_CAP_ID),
          tx.pure('vector<u8>', Array.from(proofHash)),
          tx.pure.u64(amount),
          tx.pure.u64(quantumScore),
          tx.object(SUI_CLOCK),
        ],
      });
    }

    // ── Sign & submit ──
    const result = await client.signAndExecuteTransaction({
      signer: agentKeypair,
      transaction: tx,
      options: { showEffects: true, showEvents: true },
    });

    const status = result.effects?.status?.status;
    const events = result.events?.map((ev) => ({
      type: ev.type,
      data: ev.parsedJson,
    })) ?? [];

    console.log(`✅ TX ${result.digest} — status: ${status}`);

    res.json({
      success: status === 'success',
      digest: result.digest,
      status,
      events,
      error: status !== 'success'
        ? result.effects?.status?.error
        : undefined,
    });
  } catch (e: any) {
    logError('Trade', e);
    const parsed = parseAbortError(e);
    const status = parsed.isMoveAbort ? 422 : 500;
    res.status(status).json(errorResponseBody(e));
  }
});

// ── Log quantum audit proof (standalone) ────────────────────

interface AuditRequest {
  proof_data: string;      // raw data — will be SHA-256 hashed
  amount: number;
  quantum_score?: number;
}

app.post('/api/audit', async (req: Request, res: Response) => {
  try {
    const body = req.body as AuditRequest;

    if (!body.proof_data) {
      res.status(400).json({ error: 'proof_data is required' });
      return;
    }

    const proofHash = crypto
      .createHash('sha256')
      .update(body.proof_data)
      .digest();

    const tx = new Transaction();

    tx.moveCall({
      target: `${PACKAGE_ID}::audit_trail::log_execution`,
      arguments: [
        tx.object(AGENT_CAP_ID),
        tx.pure('vector<u8>', Array.from(proofHash)),
        tx.pure.u64(body.amount ?? 0),
        tx.pure.u64(body.quantum_score ?? 0),
        tx.object(SUI_CLOCK),
      ],
    });

    const result = await client.signAndExecuteTransaction({
      signer: agentKeypair,
      transaction: tx,
      options: { showEffects: true, showEvents: true },
    });

    console.log(`📝 Audit TX: ${result.digest}`);

    res.json({
      success: result.effects?.status?.status === 'success',
      digest: result.digest,
      proof_hash_hex: proofHash.toString('hex'),
    });
  } catch (e: any) {
    logError('Audit', e);
    res.status(500).json(errorResponseBody(e));
  }
});

// ── Emergency pause (admin only) ────────────────────────────

app.post('/api/pause', async (req: Request, res: Response) => {
  if (!adminKeypair) {
    res.status(403).json({ error: 'Admin key not configured on this relayer' });
    return;
  }

  try {
    const paused = req.body.paused ?? true;

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
      signer: adminKeypair,
      transaction: tx,
      options: { showEffects: true, showEvents: true },
    });

    console.log(`${paused ? '🛑 PAUSED' : '▶️  RESUMED'} TX: ${result.digest}`);

    res.json({
      success: result.effects?.status?.status === 'success',
      digest: result.digest,
      paused,
    });
  } catch (e: any) {
    logError('Pause', e);
    res.status(500).json(errorResponseBody(e));
  }
});

// ═══════════════════════════════════════════════════════════
//  START
// ═══════════════════════════════════════════════════════════

app.listen(PORT, () => {
  console.log(`\n🚀 Relayer server running on http://localhost:${PORT}`);
  console.log(`   Network:   ${NETWORK}`);
  console.log(`   Package:   ${PACKAGE_ID}`);
  console.log(`   Portfolio:  ${PORTFOLIO_ID}`);
  console.log(`   Agent:      ${agentKeypair.getPublicKey().toSuiAddress()}`);
  console.log(`\n   Endpoints:`);
  console.log(`     POST /api/trade   — Execute quantum-optimized trade`);
  console.log(`     POST /api/audit   — Log quantum proof on-chain`);
  console.log(`     POST /api/pause   — Emergency kill-switch`);
  console.log(`     GET  /api/status  — Portfolio & gas status`);
  console.log(`     GET  /api/health  — Health check\n`);
});

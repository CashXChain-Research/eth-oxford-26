/**
 * event_provider.ts — Live Event Feeder for Person C's Frontend
 *
 * Subscribes to ALL quantum_vault on-chain events and:
 *   1. Logs them as structured JSON to stdout
 *   2. Pushes them to connected WebSocket clients in real-time
 *
 * Person C connects to ws://localhost:3002 and receives JSON events.
 *
 * Listens for:
 *   - TradeEvent           (successful trade)
 *   - QuantumTradeEvent    (quantum-verified trade)
 *   - GuardrailTriggered   (blocked trade)
 *   - RebalanceResultCreated (result object minted)
 *   - MockSwapExecuted     (DEX mock)
 *   - QuantumAuditCreated  (proof logged on-chain)
 *   - PausedChanged        (kill-switch toggled)
 *   - Deposited / Withdrawn
 *
 * Usage:
 *   npx ts-node event_provider.ts
 *   # or: npm run events
 */

import {
  SuiClient,
  getFullnodeUrl,
} from '@mysten/sui/client';
import { WebSocketServer, WebSocket } from 'ws';
import 'dotenv/config';

// ═══════════════════════════════════════════════════════════
//  CONFIG
// ═══════════════════════════════════════════════════════════

const NETWORK    = (process.env.SUI_NETWORK as 'devnet' | 'testnet' | 'mainnet') ?? 'devnet';
const RPC_URL    = process.env.SUI_RPC_URL ?? getFullnodeUrl(NETWORK);
const PACKAGE_ID = process.env.PACKAGE_ID!;

const client = new SuiClient({ url: RPC_URL });

// All event types we care about
const EVENT_TYPES = [
  `${PACKAGE_ID}::portfolio::TradeEvent`,
  `${PACKAGE_ID}::portfolio::QuantumTradeEvent`,
  `${PACKAGE_ID}::portfolio::GuardrailTriggered`,
  `${PACKAGE_ID}::portfolio::RebalanceResultCreated`,
  `${PACKAGE_ID}::portfolio::MockSwapExecuted`,
  `${PACKAGE_ID}::portfolio::PausedChanged`,
  `${PACKAGE_ID}::portfolio::Deposited`,
  `${PACKAGE_ID}::portfolio::Withdrawn`,
  `${PACKAGE_ID}::portfolio::LimitsUpdated`,
  `${PACKAGE_ID}::portfolio::AgentFrozenEvt`,
  `${PACKAGE_ID}::portfolio::AgentUnfrozenEvt`,
  `${PACKAGE_ID}::portfolio::PortfolioCreated`,
  `${PACKAGE_ID}::audit_trail::QuantumAuditCreated`,
  `${PACKAGE_ID}::audit_trail::AuditReceiptCreated`,
];

// ═══════════════════════════════════════════════════════════
//  WEBSOCKET SERVER — Person C connects here
// ═══════════════════════════════════════════════════════════

const WS_PORT = parseInt(process.env.WS_PORT ?? '3002', 10);
const wss = new WebSocketServer({ port: WS_PORT });
const wsClients = new Set<WebSocket>();

wss.on('connection', (ws) => {
  wsClients.add(ws);
  console.log(`🔗 WebSocket client connected (total: ${wsClients.size})`);

  ws.send(JSON.stringify({
    type: 'system::Connected',
    data: { message: 'Connected to quantum_vault event stream', eventTypes: EVENT_TYPES.length },
    timestamp: Date.now().toString(),
  }));

  ws.on('close', () => {
    wsClients.delete(ws);
    console.log(`🔌 WebSocket client disconnected (total: ${wsClients.size})`);
  });
  ws.on('error', () => wsClients.delete(ws));
});

/** Broadcast a structured event to ALL connected WebSocket clients */
function broadcastEvent(structured: Record<string, unknown>) {
  const json = JSON.stringify(structured);
  for (const ws of wsClients) {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(json);
    }
  }
}

// ═══════════════════════════════════════════════════════════
//  FORMATTERS
// ═══════════════════════════════════════════════════════════

function formatEvent(type: string, data: any): string {
  const shortType = type.split('::').slice(1).join('::');

  switch (shortType) {
    case 'portfolio::TradeEvent':
      return [
        `🔔 Trade #${data.trade_id}`,
        `   Agent:    ${data.agent_address}`,
        `   Amount:   ${data.input_amount} → ${data.output_amount} MIST`,
        `   Balance:  ${data.balance_before} → ${data.balance_after}`,
        `   Quantum:  ${data.is_quantum_optimized ? '⚛️  YES' : '❌ NO'}`,
      ].join('\n');

    case 'portfolio::QuantumTradeEvent':
      return [
        `⚛️  Quantum Trade #${data.trade_id}`,
        `   Agent:    ${data.agent_address}`,
        `   Amount:   ${data.input_amount} → ${data.output_amount} MIST`,
        `   Balance:  ${data.balance_before} → ${data.balance_after}`,
        `   Q-Score:  ${data.quantum_optimization_score}/100`,
        `   Quantum:  ${data.is_quantum_optimized ? '⚛️  VERIFIED' : '❌ NO'}`,
      ].join('\n');

    case 'portfolio::GuardrailTriggered':
      return [
        `🛑 GUARDRAIL BLOCKED`,
        `   Agent:     ${data.agent}`,
        `   Reason:    ${data.reason}`,
        `   Requested: ${data.requested_amount} MIST`,
        `   Vault:     ${data.vault_balance} MIST`,
      ].join('\n');

    case 'portfolio::PausedChanged':
      return data.paused
        ? '🛑 PORTFOLIO PAUSED — all trades blocked'
        : '▶️  PORTFOLIO RESUMED — trades allowed';

    case 'audit_trail::QuantumAuditCreated':
      return [
        `📝 Quantum Audit Proof`,
        `   Receipt:  ${data.receipt_id}`,
        `   Agent:    ${data.agent_address}`,
        `   Amount:   ${data.executed_amount} MIST`,
        `   Q-Score:  ${data.quantum_score}/100`,
        `   Proof:    ${data.quantum_proof_hash}`,
      ].join('\n');

    case 'portfolio::Deposited':
      return `💰 Deposited ${data.amount} MIST → balance: ${data.new_balance}`;

    case 'portfolio::Withdrawn':
      return `💸 Withdrawn ${data.amount} MIST → remaining: ${data.remaining}`;

    case 'portfolio::RebalanceResultCreated':
      return [
        `🎯 Rebalance Result`,
        `   Result ID: ${data.result_id}`,
        `   Success:   ${data.success ? '✅ YES' : '❌ NO'}`,
        `   Q-Energy:  ${data.quantum_energy}`,
        `   Trade #:   ${data.trade_id}`,
      ].join('\n');

    case 'portfolio::MockSwapExecuted':
      return [
        `🧪 Mock Swap`,
        `   Agent:    ${data.agent_address}`,
        `   Input:    ${data.input_amount} MIST`,
        `   Output:   ${data.mock_output} MIST`,
        `   Slippage: ${data.slippage_bps} bps`,
      ].join('\n');

    default:
      return `📢 ${shortType}: ${JSON.stringify(data)}`;
  }
}

// ═══════════════════════════════════════════════════════════
//  POLL-BASED EVENT WATCHER
//  (Works with any RPC — no WebSocket required)
// ═══════════════════════════════════════════════════════════

let lastSeenCursor: any = null;

async function pollEvents() {
  for (const eventType of EVENT_TYPES) {
    try {
      const events = await client.queryEvents({
        query: { MoveEventType: eventType },
        order: 'descending',
        limit: 5,
      });

      for (const ev of events.data) {
        // Simple dedup by transaction digest + event index
        const evKey = `${ev.id.txDigest}:${ev.id.eventSeq}`;
        if (seenEvents.has(evKey)) continue;
        seenEvents.add(evKey);

        const ts = new Date(parseInt(ev.timestampMs ?? '0', 10)).toISOString();
        console.log(`\n[${ts}]`);
        console.log(formatEvent(ev.type, ev.parsedJson));
        console.log(`   TX: ${ev.id.txDigest}`);

        // Emit structured JSON for frontend consumption
        const structured = {
          type: ev.type.split('::').slice(1).join('::'),
          data: ev.parsedJson,
          timestamp: ev.timestampMs,
          digest: ev.id.txDigest,
        };
        // Write to stdout as JSON (frontend can pipe/parse this)
        process.stdout.write(`\nEVENT_JSON:${JSON.stringify(structured)}\n`);
        // Push to all WebSocket clients
        broadcastEvent(structured);
      }
    } catch {
      // Ignore query errors for event types that don't exist yet
    }
  }
}

const seenEvents = new Set<string>();
const POLL_INTERVAL_MS = parseInt(process.env.EVENT_POLL_INTERVAL ?? '3000', 10);

// ═══════════════════════════════════════════════════════════
//  WEBSOCKET SUBSCRIPTION (preferred if RPC supports it)
// ═══════════════════════════════════════════════════════════

async function startWebSocket(): Promise<boolean> {
  try {
    const unsubs: (() => Promise<boolean>)[] = [];

    for (const eventType of EVENT_TYPES) {
      const unsub = await client.subscribeEvent({
        filter: { MoveEventType: eventType },
        onMessage(event) {
          const ts = new Date().toISOString();
          console.log(`\n[${ts}]`);
          console.log(formatEvent(event.type, event.parsedJson));

          const structured = {
            type: event.type.split('::').slice(1).join('::'),
            data: event.parsedJson,
            timestamp: Date.now().toString(),
          };
          process.stdout.write(`\nEVENT_JSON:${JSON.stringify(structured)}\n`);
          // Push to all WebSocket clients
          broadcastEvent(structured);
        },
      });
      unsubs.push(unsub);
    }

    console.log('📡 WebSocket subscriptions active\n');

    process.on('SIGINT', async () => {
      console.log('\n👋 Unsubscribing...');
      for (const unsub of unsubs) await unsub();
      process.exit(0);
    });

    return true;
  } catch {
    return false;
  }
}

// ═══════════════════════════════════════════════════════════
//  MAIN
// ═══════════════════════════════════════════════════════════

async function main() {
  console.log('═══════════════════════════════════════════════════');
  console.log('  📡 quantum_vault Event Provider');
  console.log('  Data source for Person C\'s frontend dashboard');
  console.log('═══════════════════════════════════════════════════');
  console.log(`  Network:    ${NETWORK}`);
  console.log(`  RPC:        ${RPC_URL}`);
  console.log(`  Package:    ${PACKAGE_ID}`);
  console.log(`  Events:     ${EVENT_TYPES.length} types`);
  console.log(`  Poll:       ${POLL_INTERVAL_MS}ms`);
  console.log(`  WebSocket:  ws://localhost:${WS_PORT}`);
  console.log(`  Clients:    ${wsClients.size} connected\n`);

  // Try WebSocket first, fall back to polling
  const wsOk = await startWebSocket();

  if (!wsOk) {
    console.log('⚠️  WebSocket not available — falling back to polling\n');
    // Initial fetch of recent events
    await pollEvents();

    // Start polling loop
    setInterval(pollEvents, POLL_INTERVAL_MS);

    process.on('SIGINT', () => {
      console.log('\n👋 Stopping event provider...');
      process.exit(0);
    });
  }
}

main().catch(console.error);

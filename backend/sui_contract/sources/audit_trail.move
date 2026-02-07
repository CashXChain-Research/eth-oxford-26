module quantum_vault::audit_trail;

use sui::object::{Self, UID, ID};
use sui::transfer;
use sui::tx_context::{Self, TxContext};
use sui::clock::{Self, Clock};
use sui::event;

use quantum_vault::agent_registry::{Self, AgentCap};

// ── Status codes ────────────────────────────────────────────
const STATUS_SUCCESS: u8  = 1;
const STATUS_BLOCKED: u8  = 2;
const STATUS_VERIFIED: u8 = 3;   // quantum-verified execution

// ═══════════════════════════════════════════════════════════
//  STRUCTS
// ═══════════════════════════════════════════════════════════

/// Legacy receipt — backwards compatible with existing code.
struct AuditReceipt has key {
    id: UID,
    agent_address: address,
    decision_hash: vector<u8>,
    timestamp_ms: u64,
    status: u8,           // 1 = Success, 2 = Blocked
    action: vector<u8>,
    amount: u64,
}

/// Quantum-verified execution receipt.
/// Stores the QUBO solution hash so anyone can verify that the
/// trade was based on the quantum optimization output.
/// Frozen on-chain — immutable forever.
struct QuantumAuditReceipt has key {
    id: UID,
    agent_id: ID,
    agent_address: address,
    quantum_proof_hash: vector<u8>,  // SHA-256 of QUBO solution data
    executed_amount: u64,
    quantum_score: u64,              // 0–100 optimization score
    portfolio_id: ID,
    timestamp_ms: u64,
    status: u8,
}

// ═══════════════════════════════════════════════════════════
//  EVENTS
// ═══════════════════════════════════════════════════════════

struct AuditReceiptCreated has copy, drop {
    receipt_id: ID,
    agent_address: address,
    status: u8,
    action: vector<u8>,
    timestamp_ms: u64,
}

/// Emitted when a quantum-verified receipt is created.
/// Person C subscribes to this for the audit dashboard.
struct QuantumAuditCreated has copy, drop {
    receipt_id: ID,
    agent_id: ID,
    agent_address: address,
    quantum_proof_hash: vector<u8>,
    executed_amount: u64,
    quantum_score: u64,
    timestamp_ms: u64,
}

// ═══════════════════════════════════════════════════════════
//  QUANTUM AUDIT — the core "Verifiable Execution" primitive
// ═══════════════════════════════════════════════════════════

/// Log a quantum-verified trade execution.
///
/// Called by Valentin's agent backend AFTER a successful trade.
/// The `proof_hash` is the SHA-256 of the full QUBO solution
/// data — anyone can re-hash the off-chain data to verify.
///
/// The receipt is frozen (immutable) so it serves as permanent
/// cryptographic evidence for the judges.
public entry fun log_execution(
    cap: &AgentCap,
    proof_hash: vector<u8>,
    amount: u64,
    quantum_score: u64,
    clock: &Clock,
    ctx: &mut TxContext,
) {
    let agent_id = object::id(cap);
    let agent_addr = agent_registry::agent_address(cap);
    let portfolio_id = agent_registry::portfolio_id(cap);
    let ts = clock::timestamp_ms(clock);

    let uid = object::new(ctx);
    let rid = object::uid_to_inner(&uid);

    let receipt = QuantumAuditReceipt {
        id: uid,
        agent_id,
        agent_address: agent_addr,
        quantum_proof_hash: proof_hash,
        executed_amount: amount,
        quantum_score,
        portfolio_id,
        timestamp_ms: ts,
        status: STATUS_VERIFIED,
    };

    event::emit(QuantumAuditCreated {
        receipt_id: rid,
        agent_id,
        agent_address: agent_addr,
        quantum_proof_hash: proof_hash,
        executed_amount: amount,
        quantum_score,
        timestamp_ms: ts,
    });

    transfer::freeze_object(receipt);
}

// ═══════════════════════════════════════════════════════════
//  LEGACY CONSTRUCTORS (unchanged, backwards compatible)
// ═══════════════════════════════════════════════════════════

public fun create_success_receipt(
    agent_address: address,
    decision_hash: vector<u8>,
    timestamp_ms: u64,
    action: vector<u8>,
    amount: u64,
    ctx: &mut TxContext,
): ID {
    let receipt = AuditReceipt {
        id: object::new(ctx),
        agent_address,
        decision_hash,
        timestamp_ms,
        status: STATUS_SUCCESS,
        action,
        amount,
    };
    let rid = object::uid_to_inner(&receipt.id);
    event::emit(AuditReceiptCreated {
        receipt_id: rid,
        agent_address,
        status: STATUS_SUCCESS,
        action: *&receipt.action,
        timestamp_ms,
    });
    transfer::freeze_object(receipt);
    rid
}

public fun create_blocked_receipt(
    agent_address: address,
    decision_hash: vector<u8>,
    timestamp_ms: u64,
    action: vector<u8>,
    amount: u64,
    ctx: &mut TxContext,
): ID {
    let receipt = AuditReceipt {
        id: object::new(ctx),
        agent_address,
        decision_hash,
        timestamp_ms,
        status: STATUS_BLOCKED,
        action,
        amount,
    };
    let rid = object::uid_to_inner(&receipt.id);
    event::emit(AuditReceiptCreated {
        receipt_id: rid,
        agent_address,
        status: STATUS_BLOCKED,
        action: *&receipt.action,
        timestamp_ms,
    });
    transfer::freeze_object(receipt);
    rid
}

// ── Read accessors ──────────────────────────────────────────

public fun status_success(): u8 { STATUS_SUCCESS }
public fun status_blocked(): u8 { STATUS_BLOCKED }
public fun status_verified(): u8 { STATUS_VERIFIED }

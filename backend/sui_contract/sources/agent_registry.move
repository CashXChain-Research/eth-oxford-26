module quantum_vault::agent_registry;

use sui::object::{Self, UID, ID};
use sui::transfer;
use sui::tx_context::{Self, TxContext};
use sui::event;

// ── Errors ──────────────────────────────────────────────────
const ENotAdmin: u64 = 0;

// ── Capabilities ────────────────────────────────────────────

/// Singleton – sent to deployer on publish.
/// Required for issuing AgentCaps and managing the portfolio.
struct AdminCap has key, store { id: UID }

/// Per-agent capability. Binds the agent to ONE specific Portfolio.
/// The agent's backend wallet must own this object to call execute_rebalance.
struct AgentCap has key, store {
    id: UID,
    agent: address,
    name: vector<u8>,
    portfolio_id: ID,       // Bound to exactly one Portfolio object
}

// ── Events ──────────────────────────────────────────────────

struct AgentIssued has copy, drop {
    agent_cap_id: ID,
    agent: address,
    name: vector<u8>,
    portfolio_id: ID,
}

struct AgentRevoked has copy, drop {
    agent_cap_id: ID,
    agent: address,
}

// ── Init ────────────────────────────────────────────────────

fun init(ctx: &mut TxContext) {
    transfer::transfer(
        AdminCap { id: object::new(ctx) },
        tx_context::sender(ctx),
    );
}

// ── Admin functions ─────────────────────────────────────────

/// Issue a new AgentCap bound to a specific Portfolio.
/// Only the AdminCap holder (Korbinian) can call this.
/// After calling, the AgentCap is transferred to `target` (Valentin).
public entry fun issue_agent_cap(
    _admin: &AdminCap,
    target: address,
    name: vector<u8>,
    portfolio_id: ID,
    ctx: &mut TxContext,
) {
    let uid = object::new(ctx);
    let cap_id = object::uid_to_inner(&uid);

    let cap = AgentCap {
        id: uid,
        agent: target,
        name,
        portfolio_id,
    };

    event::emit(AgentIssued {
        agent_cap_id: cap_id,
        agent: target,
        name,
        portfolio_id,
    });

    transfer::transfer(cap, target);
}

/// Voluntary return – the agent burns their own cap.
public entry fun revoke_own_cap(cap: AgentCap) {
    let AgentCap { id, agent, name: _, portfolio_id: _ } = cap;
    event::emit(AgentRevoked {
        agent_cap_id: object::uid_to_inner(&id),
        agent,
    });
    object::delete(id);
}

// ── Read accessors (used by portfolio.move) ─────────────────

public fun agent_address(cap: &AgentCap): address { cap.agent }
public fun agent_name(cap: &AgentCap): vector<u8> { cap.name }
public fun portfolio_id(cap: &AgentCap): ID { cap.portfolio_id }

// ── Test-only ───────────────────────────────────────────────

#[test_only]
public fun init_for_testing(ctx: &mut TxContext) { init(ctx) }

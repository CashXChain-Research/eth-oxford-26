module quantum_vault::ai_task;

use sui::object::{Self, UID};
use sui::transfer;
use sui::tx_context::{Self, TxContext};
use sui::event;
use std::vector;

use quantum_vault::agent_registry::AgentCap;

// ── Structs ─────────────────────────────────────────────────

struct Agent has store, drop {
    wallet: address,
    reputation: u64,
}

struct Task has key {
    id: UID,
    agents: vector<Agent>,
    admin: address,
}

// ── Events ──────────────────────────────────────────────────

struct TaskCreated has copy, drop {
    task_id: address,
    admin: address,
}

struct AgentRegistered has copy, drop {
    task_admin: address,
    agent: address,
    reputation: u64,
}

struct WinnerSelected has copy, drop {
    winner: address,
    random: u64,
}

// ── Init ────────────────────────────────────────────────────

fun init(ctx: &mut TxContext) {
    let admin = tx_context::sender(ctx);
    let task = Task {
        id: object::new(ctx),
        agents: vector::empty(),
        admin,
    };
    event::emit(TaskCreated { task_id: admin, admin });
    transfer::share_object(task);
}

// ── Entry functions ─────────────────────────────────────────

/// Register for a task. Requires an AgentCap (proof of authorisation).
public entry fun register_agent(
    _agent_cap: &AgentCap,
    task: &mut Task,
    reputation: u64,
    ctx: &mut TxContext,
) {
    let wallet = tx_context::sender(ctx);
    vector::push_back(&mut task.agents, Agent { wallet, reputation });
    event::emit(AgentRegistered {
        task_admin: task.admin,
        agent: wallet,
        reputation,
    });
}

/// Quantum-RNG winner selection. Admin only.
public entry fun select_winner(
    task: &mut Task,
    random_number: u64,
    ctx: &mut TxContext,
) {
    assert!(tx_context::sender(ctx) == task.admin, 0);
    let len = vector::length(&task.agents);
    assert!(len > 0, 1);

    let idx = random_number % len;
    let winner = vector::borrow(&task.agents, idx);
    event::emit(WinnerSelected { winner: winner.wallet, random: random_number });
}

module ai_task::ai_task;

use sui::object::{Self, UID};
use sui::transfer;
use sui::tx_context::{Self, TxContext};
use sui::event;
use std::vector;

struct Agent has store, drop {
    wallet: address,
    reputation: u64,
}

struct Task has key {
    id: UID,
    agents: vector<Agent>,
    admin: address,
}

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

fun init(ctx: &mut TxContext) {
    let task_addr = tx_context::sender(ctx);
    let task = Task {
        id: object::new(ctx),
        agents: vector::empty(),
        admin: task_addr,
    };
    event::emit(TaskCreated { task_id: task_addr, admin: task_addr });
    transfer::share_object(task);
}

public entry fun register_agent(task: &mut Task, reputation: u64, ctx: &mut TxContext) {
    let agent = Agent {
        wallet: tx_context::sender(ctx),
        reputation,
    };
    vector::push_back(&mut task.agents, agent);
    // Emit event so relayer knows a new agent joined
    event::emit(AgentRegistered { task_admin: task.admin, agent: tx_context::sender(ctx), reputation });
}

public entry fun select_winner(task: &mut Task, random_number: u64, ctx: &mut TxContext) {
    assert!(tx_context::sender(ctx) == task.admin, 0); // Only admin can call
    let num_agents = vector::length(&task.agents);
    assert!(num_agents > 0, 1); // At least one agent
    let winner_index = (random_number as u64) % num_agents;
    let winner = vector::borrow(&task.agents, winner_index);
    event::emit(WinnerSelected { winner: winner.wallet, random: random_number });
}
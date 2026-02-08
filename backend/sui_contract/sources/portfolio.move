module quantum_vault::portfolio;

use sui::object::{Self, UID, ID};
use sui::balance::{Self, Balance};
use sui::sui::SUI;
use sui::coin::{Self, Coin};
use sui::transfer;
use sui::tx_context::{Self, TxContext};
use sui::clock::{Self, Clock};
use sui::event;
use sui::dynamic_field;
use sui::display;
use sui::package;
use std::vector;
use std::string::{Self, String};

use quantum_vault::agent_registry::{Self, AdminCap, AgentCap};
use quantum_vault::oracle::{Self, OracleConfig};

// ── Errors ──────────────────────────────────────────────────
const EInvalidAgent: u64        = 0;
const EAgentFrozen: u64         = 1;
const ECooldownActive: u64      = 2;
const EVolumeExceeded: u64      = 3;
const EDrawdownExceeded: u64    = 4;
const EInsufficientBalance: u64 = 5;
const EPaused: u64              = 6;
const ESlippageExceeded: u64    = 7;
const EAtomicRebalanceFailed: u64 = 8;
const ESwapCountMismatch: u64     = 9;
const EPostRebalanceDrawdown: u64 = 10;
const EProtocolNotWhitelisted: u64 = 11;

// ── Defaults ────────────────────────────────────────────────
const DEFAULT_COOLDOWN_MS: u64  = 60_000;           // 60 s
const DEFAULT_DAILY_LIMIT: u64  = 50_000_000_000;   // 50 SUI in MIST
const DEFAULT_DRAWDOWN_BPS: u64 = 1_000;            // 10 %
const BPS_DENOMINATOR: u64      = 10_000;
const MS_PER_DAY: u64           = 86_400_000;

// ═══════════════════════════════════════════════════════════
//  STRUCTS
// ═══════════════════════════════════════════════════════════

struct Portfolio has key {
    id: UID,
    balance: Balance<SUI>,
    // ── Guardrails ──
    max_drawdown_bps: u64,
    daily_volume_limit: u64,
    cooldown_ms: u64,
    // ── State ──
    peak_balance: u64,
    total_traded_today: u64,
    day_start_ms: u64,
    last_trade_timestamp: u64,
    trade_count: u64,
    // ── Access control ──
    frozen_agents: vector<address>,
    // ── Protocol whitelist ──
    protocol_whitelist: vector<address>,
    // ── Emergency ──
    paused: bool,
}

// ═══════════════════════════════════════════════════════════
//  EVENTS
// ═══════════════════════════════════════════════════════════

struct PortfolioCreated has copy, drop { portfolio_id: ID }

struct Deposited has copy, drop {
    amount: u64,
    new_balance: u64,
}

struct Withdrawn has copy, drop {
    amount: u64,
    remaining: u64,
    to: address,
}

/// Rich trade event – emitted on EVERY successful trade.
/// Person C subscribes to this for the live dashboard.
struct TradeEvent has copy, drop {
    agent_id: ID,
    agent_address: address,
    input_amount: u64,
    output_amount: u64,         // same as input for now; after DEX: real output
    balance_before: u64,
    balance_after: u64,
    trade_id: u64,
    timestamp: u64,
    is_quantum_optimized: bool, // true when decision came from quantum RNG
}

/// Emitted whenever a guardrail BLOCKS a trade.
/// Frontend shows a red warning.
struct GuardrailTriggered has copy, drop {
    agent: address,
    reason: vector<u8>,
    requested_amount: u64,
    vault_balance: u64,
    timestamp_ms: u64,
}

struct AgentFrozenEvt has copy, drop { agent: address }
struct AgentUnfrozenEvt has copy, drop { agent: address }

struct LimitsUpdated has copy, drop {
    max_drawdown_bps: u64,
    daily_volume_limit: u64,
    cooldown_ms: u64,
}

/// Quantum-enhanced trade event with optimization score.
struct QuantumTradeEvent has copy, drop {
    agent_id: ID,
    agent_address: address,
    input_amount: u64,
    output_amount: u64,
    balance_before: u64,
    balance_after: u64,
    trade_id: u64,
    timestamp: u64,
    is_quantum_optimized: bool,
    quantum_optimization_score: u64,  // 0–100 from quantum RNG
}

struct PausedChanged has copy, drop { paused: bool }

/// Emitted when an atomic_rebalance completes successfully.
struct AtomicRebalanceCompleted has copy, drop {
    agent_address: address,
    num_swaps: u64,
    total_input: u64,
    total_output: u64,
    balance_before: u64,
    balance_after: u64,
    max_slippage_bps: u64,
    trade_id: u64,
    timestamp_ms: u64,
}

/// Emitted when oracle-validated swap passes.
struct OracleSwapExecuted has copy, drop {
    agent_address: address,
    amount: u64,
    oracle_price_x8: u64,
    expected_price_x8: u64,
    slippage_bps: u64,
    timestamp_ms: u64,
}

/// Result object — shared on-chain so Person C's frontend can
/// query it by ID immediately after a rebalance completes.
struct RebalanceResult has key, store {
    id: UID,
    portfolio_id: ID,
    agent_id: ID,
    success: bool,
    old_weights: vector<u64>,
    new_weights: vector<u64>,
    quantum_energy: u64,          // score from quantum solver
    input_amount: u64,
    output_amount: u64,
    timestamp_ms: u64,
    trade_id: u64,
}

struct RebalanceResultCreated has copy, drop {
    result_id: ID,
    portfolio_id: ID,
    agent_id: ID,
    success: bool,
    quantum_energy: u64,
    trade_id: u64,
}

/// Event when a mock swap is executed (DEX-less testing)
struct MockSwapExecuted has copy, drop {
    agent_address: address,
    input_amount: u64,
    mock_output: u64,
    slippage_bps: u64,
    timestamp_ms: u64,
}

/// Protocol whitelist management events
struct ProtocolWhitelisted has copy, drop { protocol: address }
struct ProtocolRemovedFromWhitelist has copy, drop { protocol: address }

/// One-time witness for Display & Publisher
struct PORTFOLIO has drop {}

// ═══════════════════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════════════════

fun init(otw: PORTFOLIO, ctx: &mut TxContext) {
    // ── Publisher for Display standard ──
    let publisher = package::claim(otw, ctx);

    // ── Display<RebalanceResult> ──
    let rebalance_display = display::new_with_fields<RebalanceResult>(
        &publisher,
        vector[
            string::utf8(b"name"),
            string::utf8(b"description"),
            string::utf8(b"project_name"),
            string::utf8(b"image_url"),
        ],
        vector[
            string::utf8(b"Rebalance #{trade_id}"),
            string::utf8(b"Quantum-optimized portfolio rebalance (energy: {quantum_energy})"),
            string::utf8(b"CashXChain Quantum Vault"),
            string::utf8(b"https://cashxchain.io/assets/rebalance_result.svg"),
        ],
        ctx,
    );
    display::update_version(&mut rebalance_display);
    transfer::public_transfer(rebalance_display, tx_context::sender(ctx));
    transfer::public_transfer(publisher, tx_context::sender(ctx));

    // ── Portfolio shared object ──
    let uid = object::new(ctx);
    let pid = object::uid_to_inner(&uid);

    let portfolio = Portfolio {
        id: uid,
        balance: balance::zero<SUI>(),
        max_drawdown_bps: DEFAULT_DRAWDOWN_BPS,
        daily_volume_limit: DEFAULT_DAILY_LIMIT,
        cooldown_ms: DEFAULT_COOLDOWN_MS,
        peak_balance: 0,
        total_traded_today: 0,
        day_start_ms: 0,
        last_trade_timestamp: 0,
        trade_count: 0,
        frozen_agents: vector::empty(),
        protocol_whitelist: vector::empty(),
        paused: false,
    };

    event::emit(PortfolioCreated { portfolio_id: pid });
    transfer::share_object(portfolio);
}

// ═══════════════════════════════════════════════════════════
//  INTERNAL: auth + guardrails
// ═══════════════════════════════════════════════════════════

/// Validate AgentCap is bound to this Portfolio and not frozen.
fun auth_agent(cap: &AgentCap, portfolio: &Portfolio): address {
    // Emergency kill-switch
    assert!(!portfolio.paused, EPaused);
    assert!(
        agent_registry::portfolio_id(cap) == object::id(portfolio),
        EInvalidAgent,
    );
    let addr = agent_registry::agent_address(cap);
    assert!(
        !vector::contains(&portfolio.frozen_agents, &addr),
        EAgentFrozen,
    );
    addr
}

/// Run all guardrail checks. Aborts on violation.
fun enforce_guardrails(
    portfolio: &mut Portfolio,
    amount: u64,
    current_time: u64,
) {
    // 1. Cooldown
    assert!(
        current_time > portfolio.last_trade_timestamp + portfolio.cooldown_ms,
        ECooldownActive,
    );

    // 2. Daily volume (rolling 24 h)
    if (current_time >= portfolio.day_start_ms + MS_PER_DAY) {
        portfolio.day_start_ms = current_time;
        portfolio.total_traded_today = 0;
    };
    assert!(
        portfolio.total_traded_today + amount <= portfolio.daily_volume_limit,
        EVolumeExceeded,
    );

    // 3. Drawdown from peak
    let current_bal = balance::value(&portfolio.balance);
    if (portfolio.peak_balance > 0 && current_bal >= amount) {
        let projected = current_bal - amount;
        let loss = portfolio.peak_balance - projected;
        let dd_bps = (loss * BPS_DENOMINATOR) / portfolio.peak_balance;
        assert!(dd_bps <= portfolio.max_drawdown_bps, EDrawdownExceeded);
    };

    // 4. Sufficient funds
    assert!(balance::value(&portfolio.balance) >= amount, EInsufficientBalance);
}

/// Book-keeping after a successful trade.
fun post_trade(portfolio: &mut Portfolio, amount: u64, current_time: u64) {
    portfolio.last_trade_timestamp = current_time;
    portfolio.total_traded_today = portfolio.total_traded_today + amount;
    portfolio.trade_count = portfolio.trade_count + 1;
}

// ═══════════════════════════════════════════════════════════
//  ADMIN: deposit / withdraw
// ═══════════════════════════════════════════════════════════

public entry fun deposit(
    _admin: &AdminCap,
    portfolio: &mut Portfolio,
    coin: Coin<SUI>,
) {
    let amount = coin::value(&coin);
    balance::join(&mut portfolio.balance, coin::into_balance(coin));
    let new_bal = balance::value(&portfolio.balance);
    if (new_bal > portfolio.peak_balance) {
        portfolio.peak_balance = new_bal;
    };
    event::emit(Deposited { amount, new_balance: new_bal });
}

public entry fun withdraw(
    _admin: &AdminCap,
    portfolio: &mut Portfolio,
    amount: u64,
    recipient: address,
    ctx: &mut TxContext,
) {
    assert!(balance::value(&portfolio.balance) >= amount, EInsufficientBalance);
    let coin = coin::from_balance(
        balance::split(&mut portfolio.balance, amount), ctx,
    );
    transfer::public_transfer(coin, recipient);
    event::emit(Withdrawn {
        amount,
        remaining: balance::value(&portfolio.balance),
        to: recipient,
    });
}

// ═══════════════════════════════════════════════════════════
//  ADMIN: guardrail tuning & freeze control
// ═══════════════════════════════════════════════════════════

public entry fun update_limits(
    _admin: &AdminCap,
    portfolio: &mut Portfolio,
    max_drawdown_bps: u64,
    daily_volume_limit: u64,
    cooldown_ms: u64,
) {
    portfolio.max_drawdown_bps = max_drawdown_bps;
    portfolio.daily_volume_limit = daily_volume_limit;
    portfolio.cooldown_ms = cooldown_ms;
    event::emit(LimitsUpdated { max_drawdown_bps, daily_volume_limit, cooldown_ms });
}

public entry fun freeze_agent(
    _admin: &AdminCap,
    portfolio: &mut Portfolio,
    agent: address,
) {
    if (!vector::contains(&portfolio.frozen_agents, &agent)) {
        vector::push_back(&mut portfolio.frozen_agents, agent);
        event::emit(AgentFrozenEvt { agent });
    };
}

public entry fun unfreeze_agent(
    _admin: &AdminCap,
    portfolio: &mut Portfolio,
    agent: address,
) {
    let (found, idx) = vector::index_of(&portfolio.frozen_agents, &agent);
    if (found) {
        vector::remove(&mut portfolio.frozen_agents, idx);
        event::emit(AgentUnfrozenEvt { agent });
    };
}

// ═══════════════════════════════════════════════════════════
//  ADMIN: emergency kill-switch
// ═══════════════════════════════════════════════════════════

public entry fun set_paused(
    _admin: &AdminCap,
    portfolio: &mut Portfolio,
    paused: bool,
) {
    portfolio.paused = paused;
    event::emit(PausedChanged { paused });
}

// ═══════════════════════════════════════════════════════════
//  ADMIN: protocol whitelist management
// ═══════════════════════════════════════════════════════════

public entry fun add_to_whitelist(
    _admin: &AdminCap,
    portfolio: &mut Portfolio,
    protocol: address,
) {
    if (!vector::contains(&portfolio.protocol_whitelist, &protocol)) {
        vector::push_back(&mut portfolio.protocol_whitelist, protocol);
        event::emit(ProtocolWhitelisted { protocol });
    };
}

public entry fun remove_from_whitelist(
    _admin: &AdminCap,
    portfolio: &mut Portfolio,
    protocol: address,
) {
    let (found, idx) = vector::index_of(&portfolio.protocol_whitelist, &protocol);
    if (found) {
        vector::remove(&mut portfolio.protocol_whitelist, idx);
        event::emit(ProtocolRemovedFromWhitelist { protocol });
    };
}

/// Check if a protocol address is whitelisted. If the whitelist is
/// empty, all protocols are allowed (permissive default for demos).
public fun is_protocol_whitelisted(portfolio: &Portfolio, protocol: address): bool {
    if (vector::is_empty(&portfolio.protocol_whitelist)) {
        return true   // empty whitelist = allow all (demo mode)
    };
    vector::contains(&portfolio.protocol_whitelist, &protocol)
}

/// Assert that a protocol is whitelisted. Aborts with EProtocolNotWhitelisted.
public fun assert_protocol_whitelisted(portfolio: &Portfolio, protocol: address) {
    assert!(is_protocol_whitelisted(portfolio, protocol), EProtocolNotWhitelisted);
}

// ═══════════════════════════════════════════════════════════
//  ADMIN: dynamic fields (extensible metadata)
//
//  Allows attaching arbitrary key-value data to the Portfolio
//  without contract upgrades. Use cases:
//    - Asset allocations, strategy parameters, external oracle configs
//    - Any typed data that future modules might need
// ═══════════════════════════════════════════════════════════

/// Attach a u64 metadata field to the Portfolio.
public entry fun set_metadata_u64(
    _admin: &AdminCap,
    portfolio: &mut Portfolio,
    key: String,
    value: u64,
) {
    if (dynamic_field::exists_(&portfolio.id, key)) {
        *dynamic_field::borrow_mut<String, u64>(&mut portfolio.id, key) = value;
    } else {
        dynamic_field::add(&mut portfolio.id, key, value);
    };
}

/// Read a u64 metadata field from the Portfolio.
public fun get_metadata_u64(portfolio: &Portfolio, key: String): u64 {
    *dynamic_field::borrow<String, u64>(&portfolio.id, key)
}

/// Attach a string metadata field to the Portfolio.
public entry fun set_metadata_string(
    _admin: &AdminCap,
    portfolio: &mut Portfolio,
    key: String,
    value: String,
) {
    if (dynamic_field::exists_(&portfolio.id, key)) {
        *dynamic_field::borrow_mut<String, String>(&mut portfolio.id, key) = value;
    } else {
        dynamic_field::add(&mut portfolio.id, key, value);
    };
}

/// Check if a metadata field exists.
public fun has_metadata(portfolio: &Portfolio, key: String): bool {
    dynamic_field::exists_(&portfolio.id, key)
}

/// Remove a u64 metadata field.
public entry fun remove_metadata_u64(
    _admin: &AdminCap,
    portfolio: &mut Portfolio,
    key: String,
) {
    if (dynamic_field::exists_(&portfolio.id, key)) {
        dynamic_field::remove<String, u64>(&mut portfolio.id, key);
    };
}

/// Remove a string metadata field.
public entry fun remove_metadata_string(
    _admin: &AdminCap,
    portfolio: &mut Portfolio,
    key: String,
) {
    if (dynamic_field::exists_(&portfolio.id, key)) {
        dynamic_field::remove<String, String>(&mut portfolio.id, key);
    };
}

// ═══════════════════════════════════════════════════════════
//  AGENT ENTRY #1:  execute_rebalance  (demo / bookkeeping)
//
//  Validates everything, emits TradeEvent, but does NOT
//  actually move SUI out of the vault. Use for dry-runs
//  and the "kill-switch" demo in the pitch.
// ═══════════════════════════════════════════════════════════

public entry fun execute_rebalance(
    cap: &AgentCap,
    portfolio: &mut Portfolio,
    amount: u64,
    is_quantum_optimized: bool,
    clock: &Clock,
    _ctx: &mut TxContext,
) {
    let agent_addr = auth_agent(cap, portfolio);
    let current_time = clock::timestamp_ms(clock);
    let bal_before = balance::value(&portfolio.balance);

    enforce_guardrails(portfolio, amount, current_time);
    post_trade(portfolio, amount, current_time);

    event::emit(TradeEvent {
        agent_id: object::id(cap),
        agent_address: agent_addr,
        input_amount: amount,
        output_amount: amount,
        balance_before: bal_before,
        balance_after: bal_before,     // no movement in demo mode
        trade_id: portfolio.trade_count,
        timestamp: current_time,
        is_quantum_optimized,
    });
}

// ═══════════════════════════════════════════════════════════
//  AGENT ENTRY #2:  withdraw_for_swap  (PTB step 1)
//
//  Returns a Coin<SUI> that the PTB passes to a DEX.
//  All guardrails are checked BEFORE the coin leaves.
// ═══════════════════════════════════════════════════════════

public fun withdraw_for_swap(
    cap: &AgentCap,
    portfolio: &mut Portfolio,
    amount: u64,
    is_quantum_optimized: bool,
    clock: &Clock,
    ctx: &mut TxContext,
): Coin<SUI> {
    let agent_addr = auth_agent(cap, portfolio);
    let current_time = clock::timestamp_ms(clock);
    let bal_before = balance::value(&portfolio.balance);

    enforce_guardrails(portfolio, amount, current_time);
    post_trade(portfolio, amount, current_time);

    let coin = coin::from_balance(
        balance::split(&mut portfolio.balance, amount), ctx,
    );

    event::emit(TradeEvent {
        agent_id: object::id(cap),
        agent_address: agent_addr,
        input_amount: amount,
        output_amount: amount,
        balance_before: bal_before,
        balance_after: balance::value(&portfolio.balance),
        trade_id: portfolio.trade_count,
        timestamp: current_time,
        is_quantum_optimized,
    });

    coin
}

// ═══════════════════════════════════════════════════════════
//  AGENT ENTRY #3:  deposit_returns  (PTB step 3)
//
//  After the DEX swap, deposit result back into the vault.
//  Updates peak_balance if vault grew.
// ═══════════════════════════════════════════════════════════

public entry fun deposit_returns(
    portfolio: &mut Portfolio,
    coin: Coin<SUI>,
    min_output: u64,
) {
    let amount = coin::value(&coin);
    // Slippage guard – revert entire PTB if DEX returned less than expected
    assert!(amount >= min_output, ESlippageExceeded);
    balance::join(&mut portfolio.balance, coin::into_balance(coin));

    let new_bal = balance::value(&portfolio.balance);
    if (new_bal > portfolio.peak_balance) {
        portfolio.peak_balance = new_bal;
    };

    event::emit(Deposited { amount, new_balance: new_bal });
}

// ═══════════════════════════════════════════════════════════
//  AGENT ENTRY #4:  swap_and_rebalance  (atomic, with slippage)
//
//  All-in-one: auth → guardrails → slippage check
//  → post_trade → emit QuantumTradeEvent.
//  Use for demo or same-module swaps. For external DEX,
//  use the PTB pattern (withdraw_for_swap → DEX → deposit_returns).
// ═══════════════════════════════════════════════════════════

public entry fun swap_and_rebalance(
    cap: &AgentCap,
    portfolio: &mut Portfolio,
    amount: u64,
    min_output: u64,
    is_quantum_optimized: bool,
    quantum_optimization_score: u64,
    clock: &Clock,
    _ctx: &mut TxContext,
) {
    let agent_addr = auth_agent(cap, portfolio);
    let current_time = clock::timestamp_ms(clock);
    let bal_before = balance::value(&portfolio.balance);

    enforce_guardrails(portfolio, amount, current_time);

    // In demo mode, output == input (no real DEX call).
    // Slippage check still fires so judges see the guardrail.
    let output_amount = amount;
    assert!(output_amount >= min_output, ESlippageExceeded);

    post_trade(portfolio, amount, current_time);

    event::emit(QuantumTradeEvent {
        agent_id: object::id(cap),
        agent_address: agent_addr,
        input_amount: amount,
        output_amount,
        balance_before: bal_before,
        balance_after: bal_before,     // no movement in demo mode
        trade_id: portfolio.trade_count,
        timestamp: current_time,
        is_quantum_optimized,
        quantum_optimization_score,
    });
}

// ═══════════════════════════════════════════════════════════
//  VIEW FUNCTIONS
// ═══════════════════════════════════════════════════════════

// ═══════════════════════════════════════════════════════════
//  RESULT OBJECT — on-chain proof of rebalancing
// ═══════════════════════════════════════════════════════════

/// Called at the END of a PTB to fix the optimization result on-chain.
/// The result is a shared object — Person C can read it by ID.
public entry fun emit_result(
    cap: &AgentCap,
    portfolio: &Portfolio,
    success: bool,
    old_weights: vector<u64>,
    new_weights: vector<u64>,
    quantum_energy: u64,
    input_amount: u64,
    output_amount: u64,
    clock: &Clock,
    ctx: &mut TxContext,
) {
    let portfolio_id = object::id(portfolio);
    let agent_id = object::id(cap);
    let uid = object::new(ctx);
    let result_id = object::uid_to_inner(&uid);
    let ts = clock::timestamp_ms(clock);

    let result = RebalanceResult {
        id: uid,
        portfolio_id,
        agent_id,
        success,
        old_weights,
        new_weights,
        quantum_energy,
        input_amount,
        output_amount,
        timestamp_ms: ts,
        trade_id: portfolio.trade_count,
    };

    event::emit(RebalanceResultCreated {
        result_id,
        portfolio_id,
        agent_id,
        success,
        quantum_energy,
        trade_id: portfolio.trade_count,
    });

    transfer::share_object(result);
}

// ═══════════════════════════════════════════════════════════
//  MOCK SWAP — DEX-less testing for Valentin
//
//  Simulates a DEX swap by withdrawing `amount`, applying a
//  configurable `slippage_bps`, and depositing back the
//  "output". No real tokens leave the vault.
// ═══════════════════════════════════════════════════════════

public entry fun mock_swap(
    cap: &AgentCap,
    portfolio: &mut Portfolio,
    amount: u64,
    slippage_bps: u64,           // e.g. 50 = 0.5% slippage
    min_output: u64,
    is_quantum_optimized: bool,
    quantum_optimization_score: u64,
    clock: &Clock,
    _ctx: &mut TxContext,
) {
    let agent_addr = auth_agent(cap, portfolio);
    let current_time = clock::timestamp_ms(clock);
    let bal_before = balance::value(&portfolio.balance);

    enforce_guardrails(portfolio, amount, current_time);

    // Simulate DEX: output = amount - slippage
    let slippage_loss = (amount * slippage_bps) / BPS_DENOMINATOR;
    let mock_output = amount - slippage_loss;
    assert!(mock_output >= min_output, ESlippageExceeded);

    // The "swap" doesn't actually move funds — vault stays intact minus slippage
    // We reduce balance by the slippage to simulate real-world loss
    if (slippage_loss > 0 && balance::value(&portfolio.balance) >= slippage_loss) {
        // Burn the slippage loss to simulate real swap friction
        let loss_bal = balance::split(&mut portfolio.balance, slippage_loss);
        balance::destroy_for_testing(loss_bal);
    };

    post_trade(portfolio, amount, current_time);

    event::emit(MockSwapExecuted {
        agent_address: agent_addr,
        input_amount: amount,
        mock_output,
        slippage_bps,
        timestamp_ms: current_time,
    });

    event::emit(QuantumTradeEvent {
        agent_id: object::id(cap),
        agent_address: agent_addr,
        input_amount: amount,
        output_amount: mock_output,
        balance_before: bal_before,
        balance_after: balance::value(&portfolio.balance),
        trade_id: portfolio.trade_count,
        timestamp: current_time,
        is_quantum_optimized,
        quantum_optimization_score,
    });
}

// ═══════════════════════════════════════════════════════════
//  VIEW FUNCTIONS
// ═══════════════════════════════════════════════════════════

public fun balance_value(p: &Portfolio): u64 { balance::value(&p.balance) }

// ═══════════════════════════════════════════════════════════
//  AGENT ENTRY #5:  oracle_validated_swap
//
//  Same as swap_and_rebalance but FIRST validates the
//  agent's expected price against the oracle price.
//  Aborts if slippage > max_slippage_bps from OracleConfig.
// ═══════════════════════════════════════════════════════════

public entry fun oracle_validated_swap(
    cap: &AgentCap,
    portfolio: &mut Portfolio,
    oracle_cfg: &OracleConfig,
    amount: u64,
    min_output: u64,
    oracle_price_x8: u64,
    expected_price_x8: u64,
    oracle_timestamp_ms: u64,
    asset_symbol: vector<u8>,
    is_quantum_optimized: bool,
    quantum_optimization_score: u64,
    clock: &Clock,
    _ctx: &mut TxContext,
) {
    let agent_addr = auth_agent(cap, portfolio);
    let current_time = clock::timestamp_ms(clock);
    let bal_before = balance::value(&portfolio.balance);

    // Oracle validation — aborts if slippage too high or price stale
    let slippage = oracle::validate_price(
        oracle_cfg,
        oracle_price_x8,
        expected_price_x8,
        oracle_timestamp_ms,
        current_time,
        agent_addr,
        copy asset_symbol,
    );

    // Standard guardrails
    enforce_guardrails(portfolio, amount, current_time);

    // Demo mode: output == input
    let output_amount = amount;
    assert!(output_amount >= min_output, ESlippageExceeded);

    post_trade(portfolio, amount, current_time);

    event::emit(OracleSwapExecuted {
        agent_address: agent_addr,
        amount,
        oracle_price_x8,
        expected_price_x8,
        slippage_bps: slippage,
        timestamp_ms: current_time,
    });

    event::emit(QuantumTradeEvent {
        agent_id: object::id(cap),
        agent_address: agent_addr,
        input_amount: amount,
        output_amount,
        balance_before: bal_before,
        balance_after: bal_before,
        trade_id: portfolio.trade_count,
        timestamp: current_time,
        is_quantum_optimized,
        quantum_optimization_score,
    });
}

// ═══════════════════════════════════════════════════════════
//  AGENT ENTRY #6:  atomic_rebalance
//
//  Takes a list of swap amounts + min outputs.
//  Executes ALL swaps atomically (all-or-nothing PTB).
//  After all swaps, verifies that the portfolio value
//  is still within safety bounds (drawdown check).
//
//  This is the core CTO function — multiple trades in
//  one transaction block.
// ═══════════════════════════════════════════════════════════

public entry fun atomic_rebalance(
    cap: &AgentCap,
    portfolio: &mut Portfolio,
    /// Amounts to swap (one per asset). Length = num_swaps.
    swap_amounts: vector<u64>,
    /// Minimum acceptable output per swap. Length = num_swaps.
    swap_min_outputs: vector<u64>,
    /// Whether this rebalance is quantum-optimized.
    is_quantum_optimized: bool,
    /// Quantum optimization score (0–100).
    quantum_optimization_score: u64,
    clock: &Clock,
    _ctx: &mut TxContext,
) {
    let agent_addr = auth_agent(cap, portfolio);
    let current_time = clock::timestamp_ms(clock);
    let bal_before = balance::value(&portfolio.balance);

    let num_swaps = vector::length(&swap_amounts);
    assert!(num_swaps == vector::length(&swap_min_outputs), ESwapCountMismatch);
    assert!(num_swaps > 0, ESwapCountMismatch);

    // ── Execute each swap atomically ──
    let total_input: u64 = 0;
    let total_output: u64 = 0;
    let max_slip: u64 = 0;
    let i: u64 = 0;

    while (i < num_swaps) {
        let amount = *vector::borrow(&swap_amounts, i);
        let min_out = *vector::borrow(&swap_min_outputs, i);

        // Guardrails per swap
        enforce_guardrails(portfolio, amount, current_time);

        // Demo: output == input (replace with DEX call in production)
        let output = amount;
        assert!(output >= min_out, ESlippageExceeded);

        // Calculate slippage for this swap
        let slip = if (amount > 0 && output < amount) {
            ((amount - output) * 10_000) / amount
        } else {
            0
        };
        if (slip > max_slip) {
            max_slip = slip;
        };

        total_input = total_input + amount;
        total_output = total_output + output;

        // Bookkeeping per swap (updates cooldown, volume, trade count)
        post_trade(portfolio, amount, current_time);

        // Emit per-swap event
        event::emit(QuantumTradeEvent {
            agent_id: object::id(cap),
            agent_address: agent_addr,
            input_amount: amount,
            output_amount: output,
            balance_before: bal_before,
            balance_after: balance::value(&portfolio.balance),
            trade_id: portfolio.trade_count,
            timestamp: current_time,
            is_quantum_optimized,
            quantum_optimization_score,
        });

        i = i + 1;
    };

    // ── Post-rebalance safety check ──
    // Verify total portfolio value hasn't dropped below drawdown limit
    let bal_after = balance::value(&portfolio.balance);
    if (portfolio.peak_balance > 0 && bal_after < portfolio.peak_balance) {
        let loss = portfolio.peak_balance - bal_after;
        let dd_bps = (loss * 10_000) / portfolio.peak_balance;
        assert!(dd_bps <= portfolio.max_drawdown_bps, EPostRebalanceDrawdown);
    };

    // ── Summary event ──
    event::emit(AtomicRebalanceCompleted {
        agent_address: agent_addr,
        num_swaps,
        total_input,
        total_output,
        balance_before: bal_before,
        balance_after: bal_after,
        max_slippage_bps: max_slip,
        trade_id: portfolio.trade_count,
        timestamp_ms: current_time,
    });
}

// ═══════════════════════════════════════════════════════════
//  AGENT ENTRY #7:  oracle_atomic_rebalance
//
//  Combines oracle validation + atomic multi-swap.
//  The "gold standard" entry point: validates every price
//  against the oracle, then executes all swaps atomically.
// ═══════════════════════════════════════════════════════════

public entry fun oracle_atomic_rebalance(
    cap: &AgentCap,
    portfolio: &mut Portfolio,
    oracle_cfg: &OracleConfig,
    swap_amounts: vector<u64>,
    swap_min_outputs: vector<u64>,
    oracle_prices_x8: vector<u64>,
    expected_prices_x8: vector<u64>,
    oracle_timestamps_ms: vector<u64>,
    asset_symbols: vector<vector<u8>>,
    is_quantum_optimized: bool,
    quantum_optimization_score: u64,
    clock: &Clock,
    _ctx: &mut TxContext,
) {
    let agent_addr = auth_agent(cap, portfolio);
    let current_time = clock::timestamp_ms(clock);

    // ── Phase 1: Oracle validation for ALL assets ──
    oracle::validate_prices_batch(
        oracle_cfg,
        &oracle_prices_x8,
        &expected_prices_x8,
        &oracle_timestamps_ms,
        &asset_symbols,
        current_time,
        agent_addr,
    );

    // ── Phase 2: Execute all swaps atomically ──
    let bal_before = balance::value(&portfolio.balance);
    let num_swaps = vector::length(&swap_amounts);
    assert!(num_swaps == vector::length(&swap_min_outputs), ESwapCountMismatch);

    let total_input: u64 = 0;
    let total_output: u64 = 0;
    let i: u64 = 0;

    while (i < num_swaps) {
        let amount = *vector::borrow(&swap_amounts, i);
        let min_out = *vector::borrow(&swap_min_outputs, i);

        enforce_guardrails(portfolio, amount, current_time);

        let output = amount;
        assert!(output >= min_out, ESlippageExceeded);

        total_input = total_input + amount;
        total_output = total_output + output;

        post_trade(portfolio, amount, current_time);

        event::emit(QuantumTradeEvent {
            agent_id: object::id(cap),
            agent_address: agent_addr,
            input_amount: amount,
            output_amount: output,
            balance_before: bal_before,
            balance_after: balance::value(&portfolio.balance),
            trade_id: portfolio.trade_count,
            timestamp: current_time,
            is_quantum_optimized,
            quantum_optimization_score,
        });

        i = i + 1;
    };

    // ── Phase 3: Post-rebalance drawdown check ──
    let bal_after = balance::value(&portfolio.balance);
    if (portfolio.peak_balance > 0 && bal_after < portfolio.peak_balance) {
        let loss = portfolio.peak_balance - bal_after;
        let dd_bps = (loss * 10_000) / portfolio.peak_balance;
        assert!(dd_bps <= portfolio.max_drawdown_bps, EPostRebalanceDrawdown);
    };

    event::emit(AtomicRebalanceCompleted {
        agent_address: agent_addr,
        num_swaps,
        total_input,
        total_output,
        balance_before: bal_before,
        balance_after: bal_after,
        max_slippage_bps: 0,
        trade_id: portfolio.trade_count,
        timestamp_ms: current_time,
    });
}

// ═══════════════════════════════════════════════════════════
//  VIEW FUNCTIONS (continued)
// ═══════════════════════════════════════════════════════════
public fun peak_balance(p: &Portfolio): u64 { p.peak_balance }
public fun max_drawdown_bps(p: &Portfolio): u64 { p.max_drawdown_bps }
public fun daily_volume_limit(p: &Portfolio): u64 { p.daily_volume_limit }
public fun cooldown_ms(p: &Portfolio): u64 { p.cooldown_ms }
public fun total_traded_today(p: &Portfolio): u64 { p.total_traded_today }
public fun last_trade_timestamp(p: &Portfolio): u64 { p.last_trade_timestamp }
public fun trade_count(p: &Portfolio): u64 { p.trade_count }
public fun is_paused(p: &Portfolio): bool { p.paused }

// ── Test-only ───────────────────────────────────────────────

#[test_only]
public fun init_for_testing(ctx: &mut TxContext) { init(PORTFOLIO {}, ctx) }

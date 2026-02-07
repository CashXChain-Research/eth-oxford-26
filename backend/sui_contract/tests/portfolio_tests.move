/// portfolio_tests.move — Unit tests for quantum_vault::portfolio
///
/// Run:   sui move test
/// (or)   sui move test --filter portfolio_tests
#[test_only]
module quantum_vault::portfolio_tests;

use sui::test_scenario::{Self as ts, Scenario};
use sui::clock::{Self, Clock};
use sui::coin::{Self, Coin};
use sui::sui::SUI;

use quantum_vault::agent_registry::{Self, AdminCap, AgentCap};
use quantum_vault::portfolio::{Self, Portfolio};

// ── Helpers ─────────────────────────────────────────────────

const ADMIN: address   = @0xAD;
const AGENT: address   = @0xA1;
const ROGUE: address   = @0xBAD;

/// Boot the whole system: publish → AdminCap + Portfolio exist.
fun setup(scenario: &mut Scenario) {
    // Transaction 1: publish — triggers init() in both modules
    ts::next_tx(scenario, ADMIN);
    {
        agent_registry::init_for_testing(ts::ctx(scenario));
        portfolio::init_for_testing(ts::ctx(scenario));
    };
}

/// Issue an AgentCap for AGENT bound to the shared Portfolio.
fun issue_cap(scenario: &mut Scenario) {
    ts::next_tx(scenario, ADMIN);
    {
        let admin_cap = ts::take_from_sender<AdminCap>(scenario);
        let portfolio = ts::take_shared<Portfolio>(scenario);
        let pid = sui::object::id(&portfolio);

        agent_registry::issue_agent_cap(
            &admin_cap,
            AGENT,
            b"valentin",
            pid,
            ts::ctx(scenario),
        );

        ts::return_to_sender(scenario, admin_cap);
        ts::return_shared(portfolio);
    };
}

/// Fund the portfolio with `amount` MIST.
fun fund(scenario: &mut Scenario, amount: u64) {
    ts::next_tx(scenario, ADMIN);
    {
        let admin_cap = ts::take_from_sender<AdminCap>(scenario);
        let mut portfolio = ts::take_shared<Portfolio>(scenario);

        let coin = coin::mint_for_testing<SUI>(amount, ts::ctx(scenario));
        portfolio::deposit(&admin_cap, &mut portfolio, coin);

        ts::return_to_sender(scenario, admin_cap);
        ts::return_shared(portfolio);
    };
}

/// Create a Clock for testing with a specific timestamp (ms).
fun create_clock(scenario: &mut Scenario, timestamp_ms: u64) {
    ts::next_tx(scenario, ADMIN);
    {
        let mut c = clock::create_for_testing(ts::ctx(scenario));
        clock::set_for_testing(&mut c, timestamp_ms);
        clock::share_for_testing(c);
    };
}

// ═══════════════════════════════════════════════════════════
//  TEST 1: Happy path — swap_and_rebalance succeeds
// ═══════════════════════════════════════════════════════════

#[test]
fun test_swap_and_rebalance_happy_path() {
    let mut scenario = ts::begin(ADMIN);
    setup(&mut scenario);
    issue_cap(&mut scenario);
    fund(&mut scenario, 10_000_000_000); // 10 SUI
    create_clock(&mut scenario, 100_000);

    // Agent calls swap_and_rebalance — 1 SUI, slippage OK
    ts::next_tx(&mut scenario, AGENT);
    {
        let cap = ts::take_from_sender<AgentCap>(&scenario);
        let mut portfolio = ts::take_shared<Portfolio>(&scenario);
        let clock = ts::take_shared<Clock>(&scenario);

        portfolio::swap_and_rebalance(
            &cap,
            &mut portfolio,
            1_000_000_000,    // 1 SUI
            900_000_000,      // min_output: 0.9 SUI (10% slippage)
            true,
            85,               // quantum_optimization_score
            &clock,
            ts::ctx(&mut scenario),
        );

        assert!(portfolio::trade_count(&portfolio) == 1);

        ts::return_to_sender(&scenario, cap);
        ts::return_shared(portfolio);
        ts::return_shared(clock);
    };
    ts::end(scenario);
}

// ═══════════════════════════════════════════════════════════
//  TEST 2: Unauthorized agent (wrong portfolio binding)
// ═══════════════════════════════════════════════════════════

#[test]
#[expected_failure(abort_code = 0)] // EInvalidAgent
fun test_unauthorized_agent() {
    let mut scenario = ts::begin(ADMIN);
    setup(&mut scenario);
    fund(&mut scenario, 10_000_000_000);
    create_clock(&mut scenario, 100_000);

    // Issue a cap for AGENT bound to a DIFFERENT portfolio ID
    ts::next_tx(&mut scenario, ADMIN);
    {
        let admin_cap = ts::take_from_sender<AdminCap>(&scenario);

        // Use a dummy ID (not the real portfolio)
        let fake_id = sui::object::id_from_address(@0xDEAD);
        agent_registry::issue_agent_cap(
            &admin_cap,
            ROGUE,
            b"rogue",
            fake_id,
            ts::ctx(&mut scenario),
        );

        ts::return_to_sender(&scenario, admin_cap);
    };

    // Rogue tries to trade → EInvalidAgent (0)
    ts::next_tx(&mut scenario, ROGUE);
    {
        let cap = ts::take_from_sender<AgentCap>(&scenario);
        let mut portfolio = ts::take_shared<Portfolio>(&scenario);
        let clock = ts::take_shared<Clock>(&scenario);

        portfolio::swap_and_rebalance(
            &cap, &mut portfolio,
            1_000_000_000, 900_000_000,
            false, 0, &clock,
            ts::ctx(&mut scenario),
        );

        ts::return_to_sender(&scenario, cap);
        ts::return_shared(portfolio);
        ts::return_shared(clock);
    };
    ts::end(scenario);
}

// ═══════════════════════════════════════════════════════════
//  TEST 3: Paused portfolio → EPaused
// ═══════════════════════════════════════════════════════════

#[test]
#[expected_failure(abort_code = 6)] // EPaused
fun test_paused_portfolio() {
    let mut scenario = ts::begin(ADMIN);
    setup(&mut scenario);
    issue_cap(&mut scenario);
    fund(&mut scenario, 10_000_000_000);
    create_clock(&mut scenario, 100_000);

    // Admin pauses the portfolio
    ts::next_tx(&mut scenario, ADMIN);
    {
        let admin_cap = ts::take_from_sender<AdminCap>(&scenario);
        let mut portfolio = ts::take_shared<Portfolio>(&scenario);

        portfolio::set_paused(&admin_cap, &mut portfolio, true);
        assert!(portfolio::is_paused(&portfolio));

        ts::return_to_sender(&scenario, admin_cap);
        ts::return_shared(portfolio);
    };

    // Agent tries to trade while paused → EPaused (6)
    ts::next_tx(&mut scenario, AGENT);
    {
        let cap = ts::take_from_sender<AgentCap>(&scenario);
        let mut portfolio = ts::take_shared<Portfolio>(&scenario);
        let clock = ts::take_shared<Clock>(&scenario);

        portfolio::swap_and_rebalance(
            &cap, &mut portfolio,
            1_000_000_000, 900_000_000,
            true, 50, &clock,
            ts::ctx(&mut scenario),
        );

        ts::return_to_sender(&scenario, cap);
        ts::return_shared(portfolio);
        ts::return_shared(clock);
    };
    ts::end(scenario);
}

// ═══════════════════════════════════════════════════════════
//  TEST 4: Slippage exceeded → ESlippageExceeded
// ═══════════════════════════════════════════════════════════

#[test]
#[expected_failure(abort_code = 7)] // ESlippageExceeded
fun test_slippage_exceeded() {
    let mut scenario = ts::begin(ADMIN);
    setup(&mut scenario);
    issue_cap(&mut scenario);
    fund(&mut scenario, 10_000_000_000);
    create_clock(&mut scenario, 100_000);

    // Agent sets min_output HIGHER than amount → guaranteed slippage fail
    ts::next_tx(&mut scenario, AGENT);
    {
        let cap = ts::take_from_sender<AgentCap>(&scenario);
        let mut portfolio = ts::take_shared<Portfolio>(&scenario);
        let clock = ts::take_shared<Clock>(&scenario);

        portfolio::swap_and_rebalance(
            &cap, &mut portfolio,
            1_000_000_000,      // input: 1 SUI
            2_000_000_000,      // min_output: 2 SUI — impossible!
            true, 50, &clock,
            ts::ctx(&mut scenario),
        );

        ts::return_to_sender(&scenario, cap);
        ts::return_shared(portfolio);
        ts::return_shared(clock);
    };
    ts::end(scenario);
}

// ═══════════════════════════════════════════════════════════
//  TEST 5: Drawdown exceeded → EDrawdownExceeded
// ═══════════════════════════════════════════════════════════

#[test]
#[expected_failure(abort_code = 4)] // EDrawdownExceeded
fun test_drawdown_exceeded() {
    let mut scenario = ts::begin(ADMIN);
    setup(&mut scenario);
    issue_cap(&mut scenario);
    fund(&mut scenario, 10_000_000_000); // 10 SUI → peak = 10 SUI
    create_clock(&mut scenario, 100_000);

    // Try to trade 5 SUI (50% of portfolio, far above 10% max drawdown)
    ts::next_tx(&mut scenario, AGENT);
    {
        let cap = ts::take_from_sender<AgentCap>(&scenario);
        let mut portfolio = ts::take_shared<Portfolio>(&scenario);
        let clock = ts::take_shared<Clock>(&scenario);

        portfolio::swap_and_rebalance(
            &cap, &mut portfolio,
            5_000_000_000,       // 5 SUI = 50% drawdown
            4_000_000_000,       // min_output
            false, 0, &clock,
            ts::ctx(&mut scenario),
        );

        ts::return_to_sender(&scenario, cap);
        ts::return_shared(portfolio);
        ts::return_shared(clock);
    };
    ts::end(scenario);
}

// ═══════════════════════════════════════════════════════════
//  TEST 6: Cooldown violation → ECooldownActive
// ═══════════════════════════════════════════════════════════

#[test]
#[expected_failure(abort_code = 2)] // ECooldownActive
fun test_cooldown_active() {
    let mut scenario = ts::begin(ADMIN);
    setup(&mut scenario);
    issue_cap(&mut scenario);
    fund(&mut scenario, 10_000_000_000);
    create_clock(&mut scenario, 100_000);

    // First trade: succeeds
    ts::next_tx(&mut scenario, AGENT);
    {
        let cap = ts::take_from_sender<AgentCap>(&scenario);
        let mut portfolio = ts::take_shared<Portfolio>(&scenario);
        let clock = ts::take_shared<Clock>(&scenario);

        portfolio::swap_and_rebalance(
            &cap, &mut portfolio,
            500_000_000,         // 0.5 SUI (safe)
            400_000_000,
            true, 75, &clock,
            ts::ctx(&mut scenario),
        );

        ts::return_to_sender(&scenario, cap);
        ts::return_shared(portfolio);
        ts::return_shared(clock);
    };

    // Second trade 1 ms later → ECooldownActive (cooldown = 60s)
    ts::next_tx(&mut scenario, AGENT);
    {
        let cap = ts::take_from_sender<AgentCap>(&scenario);
        let mut portfolio = ts::take_shared<Portfolio>(&scenario);
        let mut clock = ts::take_shared<Clock>(&scenario);

        // Advance clock by only 1 ms (still within 60s cooldown)
        clock::set_for_testing(&mut clock, 100_001);

        portfolio::swap_and_rebalance(
            &cap, &mut portfolio,
            500_000_000,
            400_000_000,
            true, 75, &clock,
            ts::ctx(&mut scenario),
        );

        ts::return_to_sender(&scenario, cap);
        ts::return_shared(portfolio);
        ts::return_shared(clock);
    };
    ts::end(scenario);
}

// ═══════════════════════════════════════════════════════════
//  TEST 7: Volume exceeded → EVolumeExceeded
// ═══════════════════════════════════════════════════════════

#[test]
#[expected_failure(abort_code = 3)] // EVolumeExceeded
fun test_volume_exceeded() {
    let mut scenario = ts::begin(ADMIN);
    setup(&mut scenario);
    issue_cap(&mut scenario);
    fund(&mut scenario, 100_000_000_000); // 100 SUI
    create_clock(&mut scenario, 100_000);

    // Lower the daily volume limit to 1 SUI for easy testing
    ts::next_tx(&mut scenario, ADMIN);
    {
        let admin_cap = ts::take_from_sender<AdminCap>(&scenario);
        let mut portfolio = ts::take_shared<Portfolio>(&scenario);

        portfolio::update_limits(
            &admin_cap, &mut portfolio,
            1_000,               // max_drawdown_bps: 10%
            1_000_000_000,       // daily_volume_limit: 1 SUI
            0,                   // cooldown: disabled for this test
        );

        ts::return_to_sender(&scenario, admin_cap);
        ts::return_shared(portfolio);
    };

    // First trade: 0.8 SUI (under 1 SUI limit) — should pass
    ts::next_tx(&mut scenario, AGENT);
    {
        let cap = ts::take_from_sender<AgentCap>(&scenario);
        let mut portfolio = ts::take_shared<Portfolio>(&scenario);
        let clock = ts::take_shared<Clock>(&scenario);

        portfolio::swap_and_rebalance(
            &cap, &mut portfolio,
            800_000_000,         // 0.8 SUI
            700_000_000,
            true, 50, &clock,
            ts::ctx(&mut scenario),
        );

        ts::return_to_sender(&scenario, cap);
        ts::return_shared(portfolio);
        ts::return_shared(clock);
    };

    // Second trade: 0.5 SUI — cumulative 1.3 SUI > 1 SUI limit → EVolumeExceeded
    ts::next_tx(&mut scenario, AGENT);
    {
        let cap = ts::take_from_sender<AgentCap>(&scenario);
        let mut portfolio = ts::take_shared<Portfolio>(&scenario);
        let mut clock = ts::take_shared<Clock>(&scenario);

        // Advance past cooldown but within same day
        clock::set_for_testing(&mut clock, 200_000);

        portfolio::swap_and_rebalance(
            &cap, &mut portfolio,
            500_000_000,         // 0.5 SUI — pushes total to 1.3 SUI
            400_000_000,
            true, 50, &clock,
            ts::ctx(&mut scenario),
        );

        ts::return_to_sender(&scenario, cap);
        ts::return_shared(portfolio);
        ts::return_shared(clock);
    };
    ts::end(scenario);
}

// ═══════════════════════════════════════════════════════════
//  TEST 8: Frozen agent → EAgentFrozen
// ═══════════════════════════════════════════════════════════

#[test]
#[expected_failure(abort_code = 1)] // EAgentFrozen
fun test_frozen_agent() {
    let mut scenario = ts::begin(ADMIN);
    setup(&mut scenario);
    issue_cap(&mut scenario);
    fund(&mut scenario, 10_000_000_000);
    create_clock(&mut scenario, 100_000);

    // Admin freezes the agent
    ts::next_tx(&mut scenario, ADMIN);
    {
        let admin_cap = ts::take_from_sender<AdminCap>(&scenario);
        let mut portfolio = ts::take_shared<Portfolio>(&scenario);

        portfolio::freeze_agent(&admin_cap, &mut portfolio, AGENT);

        ts::return_to_sender(&scenario, admin_cap);
        ts::return_shared(portfolio);
    };

    // Frozen agent tries to trade → EAgentFrozen (1)
    ts::next_tx(&mut scenario, AGENT);
    {
        let cap = ts::take_from_sender<AgentCap>(&scenario);
        let mut portfolio = ts::take_shared<Portfolio>(&scenario);
        let clock = ts::take_shared<Clock>(&scenario);

        portfolio::swap_and_rebalance(
            &cap, &mut portfolio,
            500_000_000, 400_000_000,
            true, 50, &clock,
            ts::ctx(&mut scenario),
        );

        ts::return_to_sender(&scenario, cap);
        ts::return_shared(portfolio);
        ts::return_shared(clock);
    };
    ts::end(scenario);
}

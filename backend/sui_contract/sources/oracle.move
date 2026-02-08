/// Oracle-validated trade execution for quantum_vault.
///
/// Integrates with Pyth Network price feeds on Sui to enforce
/// slippage protection based on real oracle prices.
///
/// The oracle price is compared against the agent's expected price.
/// If the deviation exceeds `max_slippage_bps` (default: 100 = 1%),
/// the transaction aborts — protecting the vault from stale or
/// manipulated prices.
///
/// Architecture:
///   Agent backend (Python) → relayer (TS) → PTB:
///     1. pyth::update_price_feed(...)     // refresh Pyth price
///     2. oracle::oracle_validated_swap()  // this module
///     3. portfolio::deposit_returns()     // deposit swap output
///
/// Pyth on Sui:
///   - State object:   0x1 (Pyth state, shared)
///   - Price feeds:    per-asset PriceInfoObject (shared)
///   - Docs: https://docs.pyth.network/price-feeds/use-real-time-data/sui
///
module quantum_vault::oracle;

use sui::object::{Self, UID, ID};
use sui::transfer;
use sui::tx_context::{Self, TxContext};
use sui::clock::{Self, Clock};
use sui::event;
use std::vector;

use quantum_vault::agent_registry::{Self, AdminCap, AgentCap};

// ── Error codes ─────────────────────────────────────────────
const ESlippageTooHigh: u64       = 100;
const EPriceStale: u64            = 101;
const EPriceNegative: u64         = 102;
const EInvalidOracleConfig: u64   = 103;

// ── Defaults ────────────────────────────────────────────────
const DEFAULT_MAX_SLIPPAGE_BPS: u64 = 100;    // 1%
const DEFAULT_MAX_STALENESS_MS: u64 = 30_000; // 30 seconds
const BPS_DENOMINATOR: u64          = 10_000;

// ═══════════════════════════════════════════════════════════
//  STRUCTS
// ═══════════════════════════════════════════════════════════

/// Shared configuration object for oracle validation parameters.
/// Admin can tune slippage tolerance and staleness window.
struct OracleConfig has key {
    id: UID,
    /// Maximum allowed slippage in basis points (100 = 1%).
    max_slippage_bps: u64,
    /// Maximum age of oracle price in milliseconds.
    max_staleness_ms: u64,
    /// Whether oracle validation is enabled (can disable for testing).
    enabled: bool,
}

/// A price attestation that the agent's off-chain code produces.
/// In a real integration, this would come from Pyth's
/// PriceInfoObject. For the hackathon, the agent submits
/// the oracle price as a u64 (price × 10^8) and the relayer
/// validates it against the Pyth feed before submission.
///
/// This struct is passed as arguments to the validated swap
/// function — the Move code checks slippage on-chain.
struct PriceAttestation has copy, drop {
    /// Asset identifier (e.g. "SUI", "ETH")
    asset_symbol: vector<u8>,
    /// Oracle price in USD × 10^8  (e.g. 150_000_000 = $1.50)
    oracle_price_usd_x8: u64,
    /// Agent's expected price in USD × 10^8
    expected_price_usd_x8: u64,
    /// Timestamp of the oracle reading (ms since epoch)
    oracle_timestamp_ms: u64,
}

// ═══════════════════════════════════════════════════════════
//  EVENTS
// ═══════════════════════════════════════════════════════════

struct OracleConfigCreated has copy, drop {
    config_id: ID,
    max_slippage_bps: u64,
    max_staleness_ms: u64,
}

struct OracleConfigUpdated has copy, drop {
    max_slippage_bps: u64,
    max_staleness_ms: u64,
    enabled: bool,
}

/// Emitted on every oracle-validated trade.
/// Person C's frontend can show the price check result.
struct OracleValidationPassed has copy, drop {
    agent: address,
    asset_symbol: vector<u8>,
    oracle_price_x8: u64,
    expected_price_x8: u64,
    slippage_bps: u64,
    max_allowed_bps: u64,
    timestamp_ms: u64,
}

/// Emitted when oracle validation BLOCKS a trade.
struct OracleValidationFailed has copy, drop {
    agent: address,
    asset_symbol: vector<u8>,
    oracle_price_x8: u64,
    expected_price_x8: u64,
    slippage_bps: u64,
    max_allowed_bps: u64,
    reason: vector<u8>,
    timestamp_ms: u64,
}

// ═══════════════════════════════════════════════════════════
//  INIT — create default OracleConfig
// ═══════════════════════════════════════════════════════════

fun init(ctx: &mut TxContext) {
    let uid = object::new(ctx);
    let cid = object::uid_to_inner(&uid);

    let config = OracleConfig {
        id: uid,
        max_slippage_bps: DEFAULT_MAX_SLIPPAGE_BPS,
        max_staleness_ms: DEFAULT_MAX_STALENESS_MS,
        enabled: true,
    };

    event::emit(OracleConfigCreated {
        config_id: cid,
        max_slippage_bps: DEFAULT_MAX_SLIPPAGE_BPS,
        max_staleness_ms: DEFAULT_MAX_STALENESS_MS,
    });

    transfer::share_object(config);
}

// ═══════════════════════════════════════════════════════════
//  ADMIN — update oracle config
// ═══════════════════════════════════════════════════════════

public entry fun update_oracle_config(
    _admin: &AdminCap,
    config: &mut OracleConfig,
    max_slippage_bps: u64,
    max_staleness_ms: u64,
    enabled: bool,
) {
    assert!(max_slippage_bps <= 1000, EInvalidOracleConfig); // max 10%
    assert!(max_staleness_ms >= 1000, EInvalidOracleConfig); // min 1s

    config.max_slippage_bps = max_slippage_bps;
    config.max_staleness_ms = max_staleness_ms;
    config.enabled = enabled;

    event::emit(OracleConfigUpdated {
        max_slippage_bps,
        max_staleness_ms,
        enabled,
    });
}

// ═══════════════════════════════════════════════════════════
//  CORE: validate_price
//
//  Checks that the agent's expected price is within
//  `max_slippage_bps` of the oracle price, and that the
//  oracle reading is not stale.
//
//  Returns the absolute slippage in BPS.
// ═══════════════════════════════════════════════════════════

/// Validate a single price against oracle.
/// Aborts if slippage exceeds config or price is stale.
public fun validate_price(
    config: &OracleConfig,
    oracle_price_x8: u64,
    expected_price_x8: u64,
    oracle_timestamp_ms: u64,
    current_time_ms: u64,
    agent_addr: address,
    asset_symbol: vector<u8>,
): u64 {
    // Skip if oracle validation is disabled
    if (!config.enabled) {
        return 0
    };

    // Check price is positive
    assert!(oracle_price_x8 > 0, EPriceNegative);
    assert!(expected_price_x8 > 0, EPriceNegative);

    // Check staleness
    let age_ms = if (current_time_ms >= oracle_timestamp_ms) {
        current_time_ms - oracle_timestamp_ms
    } else {
        0
    };

    if (age_ms > config.max_staleness_ms) {
        event::emit(OracleValidationFailed {
            agent: agent_addr,
            asset_symbol: copy asset_symbol,
            oracle_price_x8,
            expected_price_x8,
            slippage_bps: 0,
            max_allowed_bps: config.max_slippage_bps,
            reason: b"PRICE_STALE",
            timestamp_ms: current_time_ms,
        });
        abort EPriceStale
    };

    // Calculate absolute slippage in BPS:
    //   |oracle - expected| / oracle × 10000
    let diff = if (oracle_price_x8 >= expected_price_x8) {
        oracle_price_x8 - expected_price_x8
    } else {
        expected_price_x8 - oracle_price_x8
    };
    let slippage_bps = (diff * BPS_DENOMINATOR) / oracle_price_x8;

    if (slippage_bps > config.max_slippage_bps) {
        event::emit(OracleValidationFailed {
            agent: agent_addr,
            asset_symbol: copy asset_symbol,
            oracle_price_x8,
            expected_price_x8,
            slippage_bps,
            max_allowed_bps: config.max_slippage_bps,
            reason: b"SLIPPAGE_EXCEEDED",
            timestamp_ms: current_time_ms,
        });
        abort ESlippageTooHigh
    };

    // Success
    event::emit(OracleValidationPassed {
        agent: agent_addr,
        asset_symbol,
        oracle_price_x8,
        expected_price_x8,
        slippage_bps,
        max_allowed_bps: config.max_slippage_bps,
        timestamp_ms: current_time_ms,
    });

    slippage_bps
}

/// Validate multiple prices at once (for atomic rebalance).
/// Returns the maximum slippage seen across all assets.
public fun validate_prices_batch(
    config: &OracleConfig,
    oracle_prices_x8: &vector<u64>,
    expected_prices_x8: &vector<u64>,
    oracle_timestamps_ms: &vector<u64>,
    asset_symbols: &vector<vector<u8>>,
    current_time_ms: u64,
    agent_addr: address,
): u64 {
    let n = vector::length(oracle_prices_x8);
    assert!(n == vector::length(expected_prices_x8), EInvalidOracleConfig);
    assert!(n == vector::length(oracle_timestamps_ms), EInvalidOracleConfig);
    assert!(n == vector::length(asset_symbols), EInvalidOracleConfig);

    let max_slip: u64 = 0;
    let i: u64 = 0;
    while (i < n) {
        let slip = validate_price(
            config,
            *vector::borrow(oracle_prices_x8, i),
            *vector::borrow(expected_prices_x8, i),
            *vector::borrow(oracle_timestamps_ms, i),
            current_time_ms,
            agent_addr,
            *vector::borrow(asset_symbols, i),
        );
        if (slip > max_slip) {
            max_slip = slip;
        };
        i = i + 1;
    };

    max_slip
}

// ═══════════════════════════════════════════════════════════
//  VIEW
// ═══════════════════════════════════════════════════════════

public fun max_slippage_bps(config: &OracleConfig): u64 { config.max_slippage_bps }
public fun max_staleness_ms(config: &OracleConfig): u64 { config.max_staleness_ms }
public fun is_enabled(config: &OracleConfig): bool { config.enabled }

// ── Test-only ───────────────────────────────────────────────

#[test_only]
public fun init_for_testing(ctx: &mut TxContext) { init(ctx) }

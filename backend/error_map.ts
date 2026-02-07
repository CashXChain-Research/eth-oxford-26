/**
 * error_map.ts — Graceful Failure Layer
 *
 * Maps Move abort codes to frontend-friendly messages.
 * Valentin catches aborts and this module translates them.
 * Person C displays the `frontendMessage` directly in the UI.
 *
 * Usage:
 *   import { parseAbortError, ERROR_MAP } from './error_map';
 *
 *   try { ... } catch (e) {
 *     const mapped = parseAbortError(e);
 *     console.log(mapped.frontendMessage);
 *   }
 */

// ═══════════════════════════════════════════════════════════
//  ERROR CODE REGISTRY
// ═══════════════════════════════════════════════════════════

export interface MoveError {
  code: number;
  constant: string;
  module: string;
  severity: 'warning' | 'error' | 'critical';
  /** Short frontend message (DE/EN) */
  frontendMessage: string;
  /** Technical explanation for Valentin */
  devMessage: string;
  /** Suggested recovery action */
  recovery: string;
}

export const ERROR_MAP: Record<number, MoveError> = {
  0: {
    code: 0,
    constant: 'EInvalidAgent',
    module: 'portfolio',
    severity: 'critical',
    frontendMessage: '🔒 Sicherheitsfehler: Agent nicht autorisiert.',
    devMessage: 'AgentCap.portfolio_id does not match the target Portfolio object ID.',
    recovery: 'Verify AGENT_CAP_ID in .env is bound to the correct PORTFOLIO_ID. Re-issue via issue_agent_cap if needed.',
  },
  1: {
    code: 1,
    constant: 'EAgentFrozen',
    module: 'portfolio',
    severity: 'critical',
    frontendMessage: '❄️ Agent eingefroren: Admin hat diesen Agent gesperrt.',
    devMessage: 'Agent address is in the frozen_agents vector. Admin must call unfreeze_agent.',
    recovery: 'Ask Korbinian to run: sui client call --function unfreeze_agent --args <admin_cap> <portfolio> <agent_addr>',
  },
  2: {
    code: 2,
    constant: 'ECooldownActive',
    module: 'portfolio',
    severity: 'warning',
    frontendMessage: '⏳ Quanten-Cooldown: Bitte 60 Sekunden warten.',
    devMessage: 'Last trade was less than cooldown_ms ago. Current default: 60s.',
    recovery: 'Wait for the cooldown to expire, or ask admin to lower cooldown via update_limits.',
  },
  3: {
    code: 3,
    constant: 'EVolumeExceeded',
    module: 'portfolio',
    severity: 'error',
    frontendMessage: '📊 Risiko-Limit überschritten: Tägliches Volumen ausgeschöpft.',
    devMessage: 'total_traded_today + amount > daily_volume_limit. Default: 50 SUI/day.',
    recovery: 'Wait for the 24h rolling window to reset, or ask admin to raise daily_volume_limit.',
  },
  4: {
    code: 4,
    constant: 'EDrawdownExceeded',
    module: 'portfolio',
    severity: 'error',
    frontendMessage: '📉 Drawdown-Schutz: Trade würde maximalen Verlust überschreiten.',
    devMessage: 'Projected balance after trade would exceed max_drawdown_bps from peak. Default: 10%.',
    recovery: 'Reduce trade amount, or ask admin to raise max_drawdown_bps.',
  },
  5: {
    code: 5,
    constant: 'EInsufficientBalance',
    module: 'portfolio',
    severity: 'error',
    frontendMessage: '💰 Nicht genügend Guthaben im Portfolio.',
    devMessage: 'Portfolio balance < requested trade amount.',
    recovery: 'Deposit more SUI via admin deposit, or reduce trade amount.',
  },
  6: {
    code: 6,
    constant: 'EPaused',
    module: 'portfolio',
    severity: 'critical',
    frontendMessage: '🛑 Portfolio pausiert: Alle Trades sind blockiert.',
    devMessage: 'Portfolio.paused == true. Admin activated the kill switch.',
    recovery: 'Ask Korbinian to resume: POST /api/pause { "paused": false }',
  },
  7: {
    code: 7,
    constant: 'ESlippageExceeded',
    module: 'portfolio',
    severity: 'warning',
    frontendMessage: '⚠️ Slippage zu hoch: Mindest-Output nicht erreicht.',
    devMessage: 'output_amount < min_output. The DEX (or mock) returned less than expected.',
    recovery: 'Increase slippage tolerance (lower min_output) or wait for better market conditions.',
  },
};

// ═══════════════════════════════════════════════════════════
//  PARSER — extracts abort code from Sui error messages
// ═══════════════════════════════════════════════════════════

export interface ParsedError {
  isMoveAbort: boolean;
  code: number | null;
  mapped: MoveError | null;
  /** Always usable — either a mapped message or the raw error */
  frontendMessage: string;
  rawError: string;
}

/**
 * Parse a Sui transaction error (string or Error object) and
 * return a structured, frontend-friendly result.
 *
 * Handles patterns like:
 *   - "MoveAbort(_, 2)"
 *   - "abort_code: 6"
 *   - "status: { error: '...abort...2...' }"
 */
export function parseAbortError(error: unknown): ParsedError {
  const raw = error instanceof Error ? error.message : String(error);

  // Try several patterns for the abort code
  const patterns = [
    /MoveAbort\([^)]*,\s*(\d+)\)/i,
    /abort[_ ]code[:\s]+(\d+)/i,
    /Move abort (\d+)/i,
    /status_code.*?(\d+)/i,
    /VMError.*?(\d+)/i,
  ];

  for (const pat of patterns) {
    const match = raw.match(pat);
    if (match) {
      const code = parseInt(match[1], 10);
      const mapped = ERROR_MAP[code] ?? null;
      return {
        isMoveAbort: true,
        code,
        mapped,
        frontendMessage: mapped?.frontendMessage ?? `❓ Unbekannter Fehler (Code ${code})`,
        rawError: raw,
      };
    }
  }

  // Not a Move abort — return raw
  return {
    isMoveAbort: false,
    code: null,
    mapped: null,
    frontendMessage: `❌ Unerwarteter Fehler: ${raw.slice(0, 200)}`,
    rawError: raw,
  };
}

// ═══════════════════════════════════════════════════════════
//  HELPERS FOR RELAYER
// ═══════════════════════════════════════════════════════════

/** Full error response body for the relayer to send to clients */
export function errorResponseBody(error: unknown) {
  const parsed = parseAbortError(error);
  return {
    success: false,
    error: {
      isMoveAbort: parsed.isMoveAbort,
      code: parsed.code,
      constant: parsed.mapped?.constant ?? null,
      severity: parsed.mapped?.severity ?? 'error',
      message: parsed.frontendMessage,
      recovery: parsed.mapped?.recovery ?? null,
      raw: parsed.rawError,
    },
  };
}

/** Console-friendly log line */
export function logError(context: string, error: unknown): void {
  const parsed = parseAbortError(error);
  if (parsed.isMoveAbort && parsed.mapped) {
    console.error(
      `❌ [${context}] ${parsed.mapped.constant} (code ${parsed.code}): ${parsed.mapped.devMessage}`,
    );
  } else {
    console.error(`❌ [${context}] ${parsed.rawError}`);
  }
}

"use client";
// WalletConnector.js — Uses @mysten/dapp-kit-react for Slush / Sui Wallet Standard
//
// This component uses the dApp Kit hooks (useCurrentAccount, useCurrentWallet)
// which auto-detect any wallet implementing the Sui Wallet Standard (Slush, Sui Wallet, etc.)
// The <ConnectButton /> from dApp Kit renders the connect/disconnect UI.

import React, { useEffect, useRef } from "react";
import {
  ConnectButton,
  useCurrentAccount,
  useCurrentWallet,
  useCurrentNetwork,
} from "@mysten/dapp-kit-react";

/**
 * WalletConnector
 *
 * Props:
 *   onAccountChange(account | null) — called whenever the connected account changes
 */
export default function WalletConnector({ onAccountChange }) {
  const account = useCurrentAccount();
  const wallet = useCurrentWallet();
  const network = useCurrentNetwork();
  const prevAddr = useRef(null);

  // Notify parent whenever account changes
  useEffect(() => {
    const addr = account?.address ?? null;
    if (addr !== prevAddr.current) {
      prevAddr.current = addr;
      onAccountChange?.(account ?? null);
    }
  }, [account, onAccountChange]);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
      {/* dApp Kit connect button — auto-detects Slush & all Wallet-Standard wallets */}
      <ConnectButton />

      {/* Connection status */}
      {account ? (
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: "#10b981",
              boxShadow: "0 0 6px #10b981",
            }}
          />
          <span style={{ color: "#6ee7b7" }}>
            {wallet?.name ?? "Wallet"} · {network ?? "devnet"}
          </span>
          <span
            style={{
              fontFamily: "monospace",
              color: "#9ca3af",
              fontSize: 12,
              maxWidth: 180,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {account.address}
          </span>
        </div>
      ) : (
        <span style={{ fontSize: 13, color: "#6b7280" }}>
          Connect your Slush / Sui wallet to continue
        </span>
      )}
    </div>
  );
}

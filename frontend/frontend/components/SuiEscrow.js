"use client";
import React, { useState } from "react";
import WalletConnector from "./WalletConnector";

// Optional: Sui SDK — fallback to null if not installed
let TransactionBlock = null;
let JsonRpcProvider = null;
try {
  const suiModule = require("@mysten/sui");
  if (suiModule && suiModule.TransactionBlock) {
    TransactionBlock = suiModule.TransactionBlock;
  }
} catch (e) {
  // @mysten/sui not available, using fallback
}

export default function SuiEscrow({ onChainEvent }) {
  const [payer, setPayer] = useState("");
  const [payee, setPayee] = useState("");
  const [amount, setAmount] = useState("");
  const [escrowState, setEscrowState] = useState(null);
  const [log, setLog] = useState([]);
  const [wallet, setWallet] = useState(null);
  const [walletAddress, setWalletAddress] = useState(null);

  function addLog(msg) {
    setLog((l) => [...l, `${new Date().toLocaleTimeString()} — ${msg}`]);
  }

  function handleWalletConnect(info) {
    if (!info) {
      setWallet(null);
      setWalletAddress(null);
      addLog('Wallet disconnected.');
      return;
    }
    setWallet(info.wallet || null);
    setWalletAddress(info.address || null);
    addLog(`Wallet connected: ${info.address}${info.mock ? ' (mock)' : ''}`);
  }

  function createEscrow() {
    if (!payer || !payee || !amount) return addLog("Please fill in all fields.");
    const e = { payer, payee, amount, funded: false };
    setEscrowState(e);
    addLog(`Escrow created: ${amount} from ${payer} → ${payee}`);
    onChainEvent && onChainEvent({ type: 'create', payer, payee, amount, status: 'created', timestamp: Date.now() });
  }

  async function fundEscrow() {
    if (!escrowState) return addLog("No escrow exists.");
    if (escrowState.funded) return addLog("Escrow is already funded.");

    // Try on-chain via wallet when available
    if (wallet && wallet.signAndExecuteTransactionBlock) {
      try {
        addLog('Sending on-chain fund transaction...');
        const tx = new TransactionBlock();
        // For demo purposes we don't build a complex contract call; attempt a simple pay (may fail depending on wallet/provider)
        tx.transferObjects([], tx.pure(0));
        const result = await wallet.signAndExecuteTransactionBlock({ transactionBlock: tx });
        addLog(`On-chain fund transaction sent: ${result.digest || 'unknown-digest'}`);
        setEscrowState((e) => ({ ...e, funded: true }));
        onChainEvent && onChainEvent({ type: 'fund', payer: escrowState.payer, payee: escrowState.payee, amount: escrowState.amount, tx: result, status: 'funded', timestamp: Date.now() });
        return;
      } catch (e) {
        console.warn('On-chain fund failed', e);
        addLog('On-chain funding failed, falling back to simulated.');
      }
    }

    // Fallback simulated funding
    setEscrowState((e) => ({ ...e, funded: true }));
    addLog("Escrow funded (simulated).");
    onChainEvent && onChainEvent({ type: 'fund', payer: escrowState.payer, payee: escrowState.payee, amount: escrowState.amount, tx: null, status: 'funded-simulated', timestamp: Date.now() });
  }

  async function releaseEscrow() {
    if (!escrowState) return addLog("No escrow exists.");
    if (!escrowState.funded) return addLog("Escrow is not funded.");

    if (wallet && wallet.signAndExecuteTransactionBlock) {
      try {
        addLog('Sending on-chain release transaction...');
        const tx = new TransactionBlock();
        tx.transferObjects([], tx.pure(0));
        const result = await wallet.signAndExecuteTransactionBlock({ transactionBlock: tx });
        addLog(`On-chain release transaction sent: ${result.digest || 'unknown-digest'}`);
        setEscrowState(null);
        onChainEvent && onChainEvent({ type: 'release', payer: escrowState.payer, payee: escrowState.payee, amount: escrowState.amount, tx: result, status: 'released', timestamp: Date.now() });
        return;
      } catch (e) {
        console.warn('On-chain release failed', e);
        addLog('On-chain release failed, falling back to simulated.');
      }
    }

    addLog(`Escrow released: ${escrowState.amount} to ${escrowState.payee}`);
    onChainEvent && onChainEvent({ type: 'release', payer: escrowState.payer, payee: escrowState.payee, amount: escrowState.amount, tx: null, status: 'released-simulated', timestamp: Date.now() });
    setEscrowState(null);
  }

  return (
    <div style={{ marginTop: 16, padding: 12, background: "rgba(255,255,255,0.95)", borderRadius: 8, color: "#000" }}>
      <h3 style={{ marginTop: 0 }}>Sui Escrow</h3>
      <WalletConnector onConnect={handleWalletConnect} />
      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <input
          value={payer}
          onChange={(e) => setPayer(e.target.value)}
          placeholder="Payer"
          style={{ flex: 1, padding: 8, borderRadius: 6, border: "1px solid #ccc" }}
        />
        <input
          value={payee}
          onChange={(e) => setPayee(e.target.value)}
          placeholder="Payee"
          style={{ flex: 1, padding: 8, borderRadius: 6, border: "1px solid #ccc" }}
        />
        <input
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="Amount"
          style={{ width: 120, padding: 8, borderRadius: 6, border: "1px solid #ccc" }}
        />
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
        <button onClick={createEscrow} style={{ padding: "8px 12px", borderRadius: 6, background: "#0b74de", color: "#fff", border: "none" }}>
          Create Escrow
        </button>
        <button onClick={fundEscrow} style={{ padding: "8px 12px", borderRadius: 6, background: "#0a9a7b", color: "#fff", border: "none" }}>
          Fund Escrow
        </button>
        <button onClick={releaseEscrow} style={{ padding: "8px 12px", borderRadius: 6, background: "#d93b3b", color: "#fff", border: "none" }}>
          Release Escrow
        </button>
      </div>

      <div style={{ fontSize: 13, color: "#000" }}>
        <strong>Status:</strong>{' '}
        {escrowState ? `${escrowState.amount} ${escrowState.funded ? '(funded)' : '(not funded)'} — ${escrowState.payer} → ${escrowState.payee}` : 'No escrow'}
      </div>

      <div style={{ marginTop: 10, maxHeight: 120, overflow: "auto", background: "#fff", padding: 8, borderRadius: 6, border: "1px solid #eee", color: "#000" }}>
        {log.length === 0 ? <div style={{ color: '#000' }}>Log is empty.</div> : log.map((l, i) => <div key={i} style={{ fontSize: 12 }}>{l}</div>)}
      </div>
    </div>
  );
}

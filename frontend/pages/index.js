import React from "react";
import QuantumRNG from "../components/QuantumRNG";

export default function Home() {
  return (
    <div style={{ textAlign: "center", marginTop: "50px" }}>
      <h1>Willkommen zu unserem Demo-Projekt!</h1>
      <p>Quantum RNG, AI Agents und Sui Escrow – alles in einer App.</p>
      <QuantumRNG />
    </div>
  );
}

"use client";
import React, { useState } from "react";

export default function QuantumRNG() {
  const [randomNumber, setRandomNumber] = useState(null);

  function generateRandomNumber() {
    const number = Math.floor(Math.random() * 1000);
    setRandomNumber(number);
  }

  return (
    <div style={{ margin: "30px", textAlign: "center" }}>
      <h2>Quantum RNG Demo</h2>
      <button onClick={generateRandomNumber} style={{ padding: "10px 20px" }}>
        Zufallszahl erzeugen
      </button>
      {randomNumber !== null && (
        <p style={{ fontSize: "24px", marginTop: "20px" }}>
          Deine Zufallszahl: {randomNumber}
        </p>
      )}
    </div>
  );
}

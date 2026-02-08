import React, { useState } from "react";

export default function QuantumRNG() {
  const [randomNumber, setRandomNumber] = useState(null);

  function generateRandomNumber() {
    // Hier wird eine Zufallszahl erzeugt (Demo)
    const number = Math.floor(Math.random() * 1000);
    setRandomNumber(number);
  }

  return (
    <div style={{ margin: "30px", textAlign: "center" }}>
      <h2>Quantum RNG Demo</h2>
      <button onClick={generateRandomNumber} style={{ padding: "10px 20px", background: '#dc2626', color: '#fff', border: 'none', borderRadius: 999 }}>
        Zufallszahl erzeugen
      </button>
      {randomNumber !== null && (
        <p style={{ fontSize: "24px", marginTop: "20px", color: '#b91c1c' }}>
          Deine Zufallszahl: {randomNumber}
        </p>
      )}
    </div>
  );
}


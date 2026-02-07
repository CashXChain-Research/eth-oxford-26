import Image from "next/image";
import QuantumRNG from "../components/QuantumRNG";
import AIAgents from "../components/AIAgents";

export default function Home() {
  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundImage: "url('/hacker.png')",
        backgroundSize: "cover",
        backgroundPosition: "center",
      }}
      className="font-sans"
    >
      <div className="flex min-h-screen items-center justify-center p-10">
        <div className="w-[820px] max-w-full">
          <div className="text-center mb-3 text-white drop-shadow">
            <h1 className="text-2xl font-bold">Willkommen zu unserem Demo‑Projekt!</h1>
            <p className="mt-1">Quantum RNG, AI Agents und Sui Escrow — Demo</p>
          </div>

          <div className="rounded-xl overflow-hidden shadow-2xl bg-white/10 backdrop-blur-sm p-4">
            <div className="p-2">
              <QuantumRNG />
              <AIAgents bottomInputs={true} />
            </div>

            <div className="flex justify-center mt-4">
              <button className="h-12 px-6 rounded-full bg-black text-white hover:opacity-95">
                Aktion
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

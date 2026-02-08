"use client";
import Link from 'next/link';
import JohannChat from '../../components/JohannChat';

export default function FAQPage() {
  return (
    <div style={{ minHeight: '100vh', padding: 40, background: 'linear-gradient(180deg,#0f172a,#071029)', color: '#fff' }}>
      <div style={{ maxWidth: 900, margin: '0 auto', background: 'rgba(255,255,255,0.03)', padding: 24, borderRadius: 10 }}>
        <h1 style={{ marginTop: 0 }}>FAQ & Johann</h1>
        <section style={{ marginBottom: 18 }}>
          <h3>Johann (moved here)</h3>
          <p>
            Johann is an AI persona originally included in the AI Agents demo. He has been moved to
            this FAQ to keep the demo focused. You can read about his role and how the site works here.
          </p>
          <p>
            Johann's purpose: a conversational AI agent that can answer questions about the demo and provide
            guidance. For interactive AI responses, use the Tom agent in the main demo.
          </p>
          <p style={{ marginTop: 8, fontStyle: 'italic' }}>
            Reminder for Johann: Your name is Johann.
          </p>
        </section>

        <section style={{ marginBottom: 18 }}>
          <h3>Site Overview</h3>
          <ul>
            <li><strong>Quantum RNG:</strong> Demonstrates a quantum-random-number generator UI component.</li>
            <li><strong>AI Agents (Tom):</strong> Chat interface with the Tom AI agent. Tom handles user messages and on-chain event comments.</li>
            <li><strong>Sui Escrow:</strong> Demonstrates a simple escrow UI that emits simulated on-chain events the AI can comment on.</li>
          </ul>
        </section>

        <section style={{ marginBottom: 18 }}>
          <h3>How elements function</h3>
          <ul>
            <li><strong>Components:</strong> Implemented under the `components` folder. Each is a React component used on the homepage.</li>
            <li><strong>AI endpoint:</strong> Both agents call a demo AI endpoint at <span style={{ fontFamily: 'monospace' }}>https://cashxchain-ai-v1.cashxchain.workers.dev/</span>.</li>
            <li><strong>Event flow:</strong> `SuiEscrow` can emit events; the AI Agents component receives those via props and Tom will comment.</li>
          </ul>
        </section>

        <section style={{ marginBottom: 12 }}>
          <h3>Notes & Maintenance</h3>
          <ul>
            <li>Johann was removed from the live AI inputs to reduce confusion and centralize documentation here.</li>
            <li>Remove or replace the demo AI endpoint if using this in production.</li>
            <li>Unused or demo-only strings and logs were trimmed from the interactive UI.</li>
          </ul>
        </section>

        <div style={{ marginTop: 18, display: 'flex', gap: 12 }}>
          <Link href="/" style={{ padding: '10px 14px', background: '#111', color: '#fff', borderRadius: 8, textDecoration: 'none', display: 'inline-block' }}>
            Back to Demo
          </Link>
        </div>
        {/* Johann chat client component (green text, scrollable with 30px bottom gap) */}
        <div style={{ marginTop: 18 }}>
          <JohannChat />
        </div>
      </div>
    </div>
  );
}

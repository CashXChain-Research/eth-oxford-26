// Simple script to simulate repeated prompts to the demo AI endpoint
// Run: node frontend/tools/simulate_agent_repetition.js

const url = 'https://cashxchain-ai-v1.cashxchain.workers.dev/';
const fetch = global.fetch || require('node-fetch');

async function callAgent(recipient, prompt) {
  const body = { prompt, recipient, context: 'test', temperature: 0.2, max_tokens: 300 };
  try {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const txt = await res.text();
    try { return JSON.parse(txt); } catch (e) { return txt; }
  } catch (e) {
    return { error: String(e) };
  }
}

function extractReply(data) {
  if (typeof data === 'string') return data.trim();
  if (!data) return '';
  if (typeof data === 'object') return (data.reply || data.response || data.text || (data.result && data.result.response) || JSON.stringify(data)).toString().trim();
  return String(data).trim();
}

(async () => {
  const userPromptJohann = 'How do I generate a random number?';
  const userPromptTom = 'How do I fund an escrow?';
  const rounds = 6;

  console.log('Testing Johann for repeated identical consecutive replies...');
  let last = null; let duplicates = 0;
  for (let i = 0; i < rounds; i++) {
    const p = `AgentName: Johann\nPersona: Test\nUser: ${userPromptJohann}`;
    const d = await callAgent('Johann', p);
    const r = extractReply(d);
    console.log(i+1, '=>', r.substring(0, 120).replace(/\n/g, ' '));
    if (last !== null && last === r) duplicates++;
    last = r;
    await new Promise((r) => setTimeout(r, 200));
  }
  console.log('Johann duplicate consecutive replies:', duplicates, '/', rounds-1);

  console.log('\nTesting Tom for repeated identical consecutive replies...');
  last = null; duplicates = 0;
  for (let i = 0; i < rounds; i++) {
    const p = `AgentName: Tom\nPersona: Test\nUser: ${userPromptTom}`;
    const d = await callAgent('Tom', p);
    const r = extractReply(d);
    console.log(i+1, '=>', r.substring(0, 120).replace(/\n/g, ' '));
    if (last !== null && last === r) duplicates++;
    last = r;
    await new Promise((r) => setTimeout(r, 200));
  }
  console.log('Tom duplicate consecutive replies:', duplicates, '/', rounds-1);

  console.log('\nDone.');
})();

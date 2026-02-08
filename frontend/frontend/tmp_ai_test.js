const fetch = global.fetch || (await import('node-fetch')).default;
(async () => {
  const endpoint = 'https://cashxchain-ai-v1.cashxchain.workers.dev/';
  const body = {
    prompt: `You are MarketQuantumExecutor. Answer concisely and directly. Use at most 2 sentences.\n\nSimulate market buy of 100 SUI at market price; output steps and estimated cost`,
    recipient: 'MarketQuantumExecutor',
    temperature: 0.05,
    max_tokens: 150,
  };
  try {
    const r = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const text = await r.text();
    console.log('STATUS', r.status);
    let parsed;
    try { parsed = JSON.parse(text); console.log('RAW JSON response logged'); } catch (e) { console.log('RAW:', text); parsed = null; }
    const raw = parsed && (parsed.result?.response || parsed.choices?.[0]?.text || parsed.text || parsed.reply || text);
    function shorten(s) {
      if (!s) return '';
      const para = String(s).split(/\n\s*\n/)[0];
      const sentences = para.match(/[^.!?]+[.!?]?/g) || [para];
      return sentences.slice(0,2).join(' ').trim();
    }
    console.log('SHORT:', shorten(raw));
  } catch (e) {
    console.error('FETCH ERROR', e);
  }
})();

How to test Sign-in with Wallet (Demo)

1. Start dev server:

   cd frontend/frontend
   npm run dev

2. Open http://localhost:3000 in your browser.

3. Connect a browser Sui-compatible wallet (e.g., Sui Wallet extension).

4. Click `Connect`. If your wallet supports signing, the app will auto-prompt to sign a demo challenge. Approve the signature.

5. After signing the app will send the signature to `/api/verify`, which responds and sets a `session` cookie (demo JWT).

Notes:
- If you don't have a wallet, use `View demo portfolio` to see demo data.
- Server does a demo-accept if `@mysten/sui.js` isn't available.
- For production, set `JWT_SECRET` in environment variables and implement robust verification using the wallet SDK.

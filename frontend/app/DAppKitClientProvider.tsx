// DAppKitClientProvider.tsx — Client-only wrapper (wallets need browser window)
'use client';

import { DAppKitProvider, ConnectButton } from '@mysten/dapp-kit-react';
import { dAppKit } from './dapp-kit';

export function DAppKitClientProvider({ children }: { children: React.ReactNode }) {
  return <DAppKitProvider dAppKit={dAppKit}>{children}</DAppKitProvider>;
}

export { ConnectButton };

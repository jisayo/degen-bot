'use client';

import { Radio, ShieldAlert, ShieldCheck, CheckCircle2, AlertTriangle, ExternalLink } from 'lucide-react';
import { formatCurrency, formatNumber, truncateAddress } from '@/lib/formatters';

export default function ScannerPage() {
  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#231f4b] pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center space-x-2">
            <Radio className="w-5 h-5 text-purple-400 animate-pulse" />
            <span>SOLANA TOKEN RADAR & SCANNER</span>
          </h1>
          <p className="text-xs text-zinc-400 mt-1">
            Real-time candidate discovery from DexScreener &bull; 1–5 min age filter &bull; RugCheck risk screening
          </p>
        </div>

        <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-emerald-950/40 border border-emerald-800 text-xs font-mono text-emerald-300">
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
          <span>RADAR ACTIVE</span>
        </div>
      </div>

      {/* Filter Thresholds Info Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 font-mono text-xs">
        <div className="terminal-card rounded-xl p-4">
          <span className="text-zinc-400 uppercase text-[11px]">Age Window</span>
          <div className="text-base font-bold text-zinc-100 mt-1">1 &ndash; 5 Minutes</div>
          <span className="text-[10px] text-zinc-500">Ignores older seasoned pools</span>
        </div>
        <div className="terminal-card rounded-xl p-4">
          <span className="text-zinc-400 uppercase text-[11px]">Min Liq / MC</span>
          <div className="text-base font-bold text-purple-300 mt-1">&gt;= 50%</div>
          <span className="text-[10px] text-zinc-500">Prevents low liquidity traps</span>
        </div>
        <div className="terminal-card rounded-xl p-4">
          <span className="text-zinc-400 uppercase text-[11px]">Min Trades</span>
          <div className="text-base font-bold text-zinc-100 mt-1">20 Transactions</div>
          <span className="text-[10px] text-zinc-500">Combined 1h buys + sells</span>
        </div>
        <div className="terminal-card rounded-xl p-4">
          <span className="text-zinc-400 uppercase text-[11px]">Rug Risk Filter</span>
          <div className="text-base font-bold text-emerald-400 mt-1">LOW Risk Only</div>
          <span className="text-[10px] text-zinc-500">Verified via RugCheck API</span>
        </div>
      </div>

      {/* Live radar explanation card */}
      <div className="terminal-card rounded-xl p-6 text-center space-y-3">
        <div className="w-12 h-12 rounded-full bg-purple-900/30 border border-purple-600/40 mx-auto flex items-center justify-center">
          <Radio className="w-6 h-6 text-purple-400 animate-pulse" />
        </div>
        <h3 className="text-base font-bold text-white">Live Scanner Connected to DexScreener & RugCheck</h3>
        <p className="text-xs text-zinc-400 max-w-lg mx-auto">
          The scanner runs inside the background Python bot loop (<code className="text-purple-300">src/main.py</code>). When a newly minted Solana pool meets the 1-5m age window, liquidity criteria, and passes RugCheck verification, it is automatically routed to the paper trader.
        </p>
        <div className="pt-2">
          <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full text-xs font-mono bg-purple-950 border border-purple-800 text-purple-300">
            <span>Terminal status: Ready to receive real-time events</span>
          </span>
        </div>
      </div>
    </div>
  );
}

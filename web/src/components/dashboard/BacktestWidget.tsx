'use client';

import { BacktestAggregate, BacktestTrade } from '@/lib/types';
import { formatCurrency, formatPercent, truncateAddress } from '@/lib/formatters';
import { ShieldCheck, ArrowUpRight, ArrowDownRight, Layers } from 'lucide-react';

interface BacktestWidgetProps {
  aggregate: BacktestAggregate | null;
  trades: BacktestTrade[];
  loading?: boolean;
}

export default function BacktestWidget({ aggregate, trades, loading }: BacktestWidgetProps) {
  if (loading) {
    return (
      <div className="terminal-card rounded-xl p-6 text-center text-zinc-500">
        Loading backtest results...
      </div>
    );
  }

  if (!aggregate) {
    return (
      <div className="terminal-card rounded-xl p-6 text-center text-zinc-500">
        No single-wallet backtest run found.
      </div>
    );
  }

  const exitReasons = aggregate.exit_reasons || {};

  return (
    <div className="terminal-card rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-[#231f4b] flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-100 flex items-center space-x-2">
            <span>Single $50 Wallet Simulation Benchmark</span>
            <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-950 text-emerald-400 font-mono border border-emerald-800">
              {formatPercent(aggregate.return_pct)} Net
            </span>
          </h2>
          <p className="text-xs text-zinc-400 mt-0.5">
            Tested across {aggregate.trades_executed} clean-cohort pools using 20% trade allocations
          </p>
        </div>
      </div>

      <div className="p-5 grid grid-cols-2 md:grid-cols-4 gap-4 bg-[#0a0918]/60 border-b border-[#231f4b]">
        <div>
          <span className="text-[11px] text-zinc-400 uppercase font-mono">Final Balance</span>
          <div className="text-xl font-bold font-mono text-zinc-100">
            {formatCurrency(aggregate.final_balance)}
          </div>
          <span className="text-[10px] text-zinc-400">From $50.00 base</span>
        </div>

        <div>
          <span className="text-[11px] text-zinc-400 uppercase font-mono">Total Net P/L</span>
          <div className="text-xl font-bold font-mono text-emerald-400">
            +{formatCurrency(aggregate.total_net_pnl)}
          </div>
          <span className="text-[10px] text-emerald-400 font-medium">
            {formatPercent(aggregate.return_pct)} gain
          </span>
        </div>

        <div>
          <span className="text-[11px] text-zinc-400 uppercase font-mono">Win Rate</span>
          <div className="text-xl font-bold font-mono text-purple-300">
            {aggregate.win_rate_pct.toFixed(1)}%
          </div>
          <span className="text-[10px] text-zinc-400">
            {aggregate.wins} W / {aggregate.losses} L
          </span>
        </div>

        <div>
          <span className="text-[11px] text-zinc-400 uppercase font-mono">Max Drawdown</span>
          <div className="text-xl font-bold font-mono text-rose-400">
            {aggregate.max_drawdown_pct.toFixed(1)}%
          </div>
          <span className="text-[10px] text-zinc-400">Peak-to-trough</span>
        </div>
      </div>

      {/* Exit Reason breakdown */}
      <div className="px-5 py-3 border-b border-[#231f4b] flex flex-wrap items-center gap-2 text-xs font-mono">
        <span className="text-zinc-400 mr-2 text-[11px] uppercase">Exit Reasons:</span>
        {Object.entries(exitReasons).map(([reason, count]) => {
          const isProfitable = reason === 'TAKE_PROFIT' || reason === 'TRAILING_STOP' || reason === 'TRAILING_TAKE_PROFIT' || reason === 'END_OF_DATA';
          return (
            <span
              key={reason}
              className={`px-2 py-0.5 rounded text-[11px] border ${
                isProfitable
                  ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800/60'
                  : 'bg-rose-950/40 text-rose-300 border-rose-900/50'
              }`}
            >
              {reason}: <strong className="ml-1">{count}</strong>
            </span>
          );
        })}
      </div>

      {/* Recent trades list */}
      <div className="overflow-x-auto max-h-72 overflow-y-auto">
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-[#0b0a1a] text-zinc-400 uppercase tracking-wider sticky top-0 border-b border-[#231f4b]">
            <tr>
              <th className="py-2.5 px-4">Pool</th>
              <th className="py-2.5 px-4">Allocation</th>
              <th className="py-2.5 px-4">Exit Reason</th>
              <th className="py-2.5 px-4">Net P/L</th>
              <th className="py-2.5 px-4 text-right">Wallet Cash</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1e1a3f]">
            {trades.slice(0, 15).map((t, i) => {
              const isWin = t.net_pnl > 0;
              return (
                <tr key={i} className="hover:bg-purple-950/10">
                  <td className="py-2 px-4 text-purple-300">
                    {truncateAddress(t.pool, 5)}
                  </td>
                  <td className="py-2 px-4 text-zinc-300">
                    {formatCurrency(t.allocation)}
                  </td>
                  <td className="py-2 px-4 text-zinc-400">
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-zinc-900 text-zinc-300 border border-zinc-800">
                      {t.exit_reason}
                    </span>
                  </td>
                  <td className={`py-2 px-4 font-semibold ${isWin ? 'text-emerald-400' : 'text-rose-400'}`}>
                    <div className="flex items-center space-x-1">
                      {isWin ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                      <span>{isWin ? '+' : ''}{formatCurrency(t.net_pnl)}</span>
                    </div>
                  </td>
                  <td className="py-2 px-4 text-right text-zinc-200">
                    {formatCurrency(t.wallet_cash)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

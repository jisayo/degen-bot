'use client';

import { PaperTrade } from '@/lib/types';
import { formatCurrency, formatTimeAgo, truncateAddress } from '@/lib/formatters';
import { CheckCircle2, XCircle, ArrowUpRight, ArrowDownRight, ExternalLink, History } from 'lucide-react';

interface LiveTradesTableProps {
  trades: PaperTrade[];
  loading?: boolean;
}

export default function LiveTradesTable({ trades, loading }: LiveTradesTableProps) {
  return (
    <div className="terminal-card rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-[#231f4b] flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-100 flex items-center space-x-2">
            <History className="w-4 h-4 text-purple-400" />
            <span>Completed Trades (7-Day Trial)</span>
            <span className="px-2 py-0.5 rounded-full text-[10px] bg-purple-900/40 text-purple-300 font-mono border border-purple-700/40">
              {trades.length} Closed
            </span>
          </h2>
          <p className="text-xs text-zinc-400 mt-0.5">
            Realized paper trade executions from the current $50.00 trial run.
          </p>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-[#0b0a1a] text-zinc-400 uppercase tracking-wider font-mono border-b border-[#231f4b]">
            <tr>
              <th className="py-3 px-4">Time</th>
              <th className="py-3 px-4">Token Address</th>
              <th className="py-3 px-4">Entry</th>
              <th className="py-3 px-4">Exit</th>
              <th className="py-3 px-4">Size</th>
              <th className="py-3 px-4">Net P/L</th>
              <th className="py-3 px-4">Exit Reason</th>
              <th className="py-3 px-4 text-right">Balance</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1e1a3f] font-mono">
            {loading ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-zinc-500">
                  Loading trade history...
                </td>
              </tr>
            ) : trades.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-zinc-500">
                  No trades closed yet in this 7-day test. Active positions are currently monitored.
                </td>
              </tr>
            ) : (
              trades.map((trade, idx) => {
                const isProfit = Number(trade.pnl) > 0;
                const pnl = Number(trade.pnl) || 0;
                const entry = Number(trade.entry_price) || 0;
                const exit = Number(trade.exit_price) || 0;
                const pnlPct = entry > 0 ? ((exit - entry) / entry) * 100 : 0;
                const balance = Number(trade.balance) || 50;

                return (
                  <tr key={idx} className="hover:bg-[#14122b] transition-colors">
                    <td className="py-3 px-4 text-zinc-400">
                      {trade.timestamp ? formatTimeAgo(trade.timestamp) : 'Just now'}
                    </td>
                    <td className="py-3 px-4 text-zinc-200">
                      <a
                        href={`https://dexscreener.com/solana/${trade.token}`}
                        target="_blank"
                        rel="noreferrer"
                        className="hover:text-purple-400 flex items-center space-x-1"
                      >
                        <span>{truncateAddress(String(trade.token))}</span>
                        <ExternalLink className="w-3 h-3 text-zinc-500" />
                      </a>
                    </td>
                    <td className="py-3 px-4 text-zinc-300">
                      ${Number(trade.entry_price).toFixed(6)}
                    </td>
                    <td className="py-3 px-4 text-zinc-300">
                      ${Number(trade.exit_price).toFixed(6)}
                    </td>
                    <td className="py-3 px-4 text-zinc-300">
                      ${Number(trade.trade_size).toFixed(2)}
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center space-x-1 font-semibold ${
                          isProfit ? 'text-emerald-400' : 'text-rose-400'
                        }`}
                      >
                        {isProfit ? (
                          <ArrowUpRight className="w-3.5 h-3.5" />
                        ) : (
                          <ArrowDownRight className="w-3.5 h-3.5" />
                        )}
                        <span>
                          {pnl >= 0 ? '+' : ''}${pnl.toFixed(4)} ({pnlPct >= 0 ? '+' : ''}
                          {pnlPct.toFixed(2)}%)
                        </span>
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                          isProfit
                            ? 'bg-emerald-950/60 text-emerald-400 border-emerald-800'
                            : 'bg-rose-950/60 text-rose-400 border-rose-800'
                        }`}
                      >
                        {trade.reason || (isProfit ? 'TRAILING_TAKE_PROFIT' : 'STOP_LOSS')}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right font-bold text-white">
                      ${balance.toFixed(2)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

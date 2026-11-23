'use client';

import { useEffect, useState } from 'react';
import { BacktestAggregate, BacktestTrade } from '@/lib/types';
import { formatCurrency, formatPercent, truncateAddress } from '@/lib/formatters';
import { LineChart, ArrowUpRight, ArrowDownRight, Filter, Download } from 'lucide-react';

export default function BacktestPage() {
  const [data, setData] = useState<{ aggregate: BacktestAggregate | null; trades: BacktestTrade[] }>({
    aggregate: null,
    trades: [],
  });
  const [loading, setLoading] = useState(true);
  const [filterReason, setFilterReason] = useState<string>('ALL');

  useEffect(() => {
    async function loadBacktest() {
      try {
        const res = await fetch('/api/backtest');
        if (res.ok) {
          const json = await res.json();
          setData({
            aggregate: json.aggregate || null,
            trades: json.trades || [],
          });
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    loadBacktest();
  }, []);

  const agg = data.aggregate;
  const filteredTrades = data.trades.filter((t) => {
    if (filterReason === 'ALL') return true;
    if (filterReason === 'WINS') return t.net_pnl > 0;
    if (filterReason === 'LOSSES') return t.net_pnl <= 0;
    return t.exit_reason === filterReason;
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#231f4b] pb-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white flex items-center space-x-2">
            <LineChart className="w-5 h-5 text-purple-400" />
            <span>HISTORICAL BACKTEST HUB</span>
          </h1>
          <p className="text-xs text-zinc-400 mt-1">
            Single $50 Wallet &bull; Solana Trailing Stop Strategy (15% Post-Activation Ratchet, Jito Bundles)
          </p>
        </div>

        {agg && (
          <div className="flex items-center space-x-3 font-mono text-xs">
            <div className="px-3 py-1.5 rounded-lg bg-emerald-950/40 border border-emerald-800/60 text-emerald-400">
              Return: <strong>{formatPercent(agg.return_pct)}</strong>
            </div>
            <div className="px-3 py-1.5 rounded-lg bg-purple-950/40 border border-purple-800/60 text-purple-300">
              Win Rate: <strong>{agg.win_rate_pct.toFixed(1)}%</strong>
            </div>
          </div>
        )}
      </div>

      {loading ? (
        <div className="terminal-card rounded-xl p-12 text-center text-zinc-500 font-mono">
          Loading backtest datasets...
        </div>
      ) : !agg ? (
        <div className="terminal-card rounded-xl p-12 text-center text-zinc-500 font-mono">
          No backtest results found.
        </div>
      ) : (
        <>
          {/* Summary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="terminal-card rounded-xl p-4">
              <span className="text-[11px] text-zinc-400 uppercase font-mono">Base Capital</span>
              <div className="text-xl font-bold font-mono text-zinc-200 mt-1">
                {formatCurrency(agg.starting_balance)}
              </div>
              <span className="text-[10px] text-zinc-500 font-mono">Starting balance</span>
            </div>

            <div className="terminal-card rounded-xl p-4">
              <span className="text-[11px] text-zinc-400 uppercase font-mono">Final Balance</span>
              <div className="text-xl font-bold font-mono text-emerald-400 mt-1">
                {formatCurrency(agg.final_balance)}
              </div>
              <span className="text-[10px] text-emerald-400 font-mono">
                +{formatCurrency(agg.total_net_pnl)} Net Profit
              </span>
            </div>

            <div className="terminal-card rounded-xl p-4">
              <span className="text-[11px] text-zinc-400 uppercase font-mono">Total Trades</span>
              <div className="text-xl font-bold font-mono text-purple-300 mt-1">
                {agg.trades_executed}
              </div>
              <span className="text-[10px] text-zinc-500 font-mono">
                {agg.wins} Wins / {agg.losses} Losses
              </span>
            </div>

            <div className="terminal-card rounded-xl p-4">
              <span className="text-[11px] text-zinc-400 uppercase font-mono">Max Drawdown</span>
              <div className="text-xl font-bold font-mono text-rose-400 mt-1">
                {agg.max_drawdown_pct.toFixed(1)}%
              </div>
              <span className="text-[10px] text-zinc-500 font-mono">Portfolio peak to trough</span>
            </div>
          </div>

          {/* Filter Bar */}
          <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-[#0e0c21] border border-[#231f4b]">
            <div className="flex items-center space-x-2 text-xs font-mono">
              <Filter className="w-3.5 h-3.5 text-zinc-400" />
              <span className="text-zinc-400 uppercase">Filter:</span>
              {['ALL', 'WINS', 'LOSSES', 'TRAILING_TAKE_PROFIT', 'STOP_LOSS', 'END_OF_DATA', 'TRAILING_STOP', 'TAKE_PROFIT'].map((f) => (
                <button
                  key={f}
                  onClick={() => setFilterReason(f)}
                  className={`px-2.5 py-1 rounded text-[11px] transition-all ${
                    filterReason === f
                      ? 'bg-purple-900/60 text-purple-200 border border-purple-600'
                      : 'bg-[#15122e] text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>

            <span className="text-xs font-mono text-zinc-400">
              Showing {filteredTrades.length} of {data.trades.length} trades
            </span>
          </div>

          {/* Trades Detailed Table */}
          <div className="terminal-card rounded-xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-[#0b0a1a] text-zinc-400 uppercase tracking-wider border-b border-[#231f4b]">
                  <tr>
                    <th className="py-3 px-4">Pool Address</th>
                    <th className="py-3 px-4">Entry Price</th>
                    <th className="py-3 px-4">Exit Price</th>
                    <th className="py-3 px-4">Peak Gain</th>
                    <th className="py-3 px-4">Allocation</th>
                    <th className="py-3 px-4">Fees</th>
                    <th className="py-3 px-4">Exit Reason</th>
                    <th className="py-3 px-4">Net P/L</th>
                    <th className="py-3 px-4 text-right">Wallet Cash</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1e1a3f]">
                  {filteredTrades.map((t, idx) => {
                    const isWin = t.net_pnl > 0;
                    return (
                      <tr key={idx} className="hover:bg-purple-950/20">
                        <td className="py-2.5 px-4 text-purple-300 font-semibold">
                          <a
                            href={`https://dexscreener.com/solana/${t.pool}`}
                            target="_blank"
                            rel="noreferrer"
                            className="hover:underline"
                          >
                            {truncateAddress(t.pool, 6)}
                          </a>
                        </td>
                        <td className="py-2.5 px-4 text-zinc-300">
                          {formatCurrency(t.entry_price, 6)}
                        </td>
                        <td className="py-2.5 px-4 text-zinc-300">
                          {formatCurrency(t.exit_price, 6)}
                        </td>
                        <td className="py-2.5 px-4 font-mono text-xs">
                          {t.peak_gain_pct !== undefined ? (
                            <span className={t.peak_gain_pct > 15 ? 'text-emerald-400 font-bold' : 'text-zinc-400'}>
                              +{t.peak_gain_pct.toFixed(1)}%
                            </span>
                          ) : (
                            <span className="text-zinc-500">-</span>
                          )}
                        </td>
                        <td className="py-2.5 px-4 text-zinc-200 font-medium">
                          {formatCurrency(t.allocation)}
                        </td>
                        <td className="py-2.5 px-4 text-zinc-400">
                          {formatCurrency(t.entry_fee + t.exit_fee, 4)}
                        </td>
                        <td className="py-2.5 px-4">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                              t.exit_reason === 'TAKE_PROFIT' || t.exit_reason === 'TRAILING_STOP' || t.exit_reason === 'TRAILING_TAKE_PROFIT'
                                ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                                : 'bg-rose-950 text-rose-400 border border-rose-900'
                            }`}
                          >
                            {t.exit_reason}
                          </span>
                        </td>
                        <td
                          className={`py-2.5 px-4 font-semibold ${
                            isWin ? 'text-emerald-400' : 'text-rose-400'
                          }`}
                        >
                          <div className="flex items-center space-x-1">
                            {isWin ? <ArrowUpRight className="w-3.5 h-3.5" /> : <ArrowDownRight className="w-3.5 h-3.5" />}
                            <span>{isWin ? '+' : ''}{formatCurrency(t.net_pnl)}</span>
                          </div>
                        </td>
                        <td className="py-2.5 px-4 text-right text-zinc-200 font-bold">
                          {formatCurrency(t.wallet_cash)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

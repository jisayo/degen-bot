"use client";

import { Position } from "@/lib/types";
import {
  formatCurrency,
  formatPercent,
  truncateAddress,
  formatTimeAgo,
} from "@/lib/formatters";
import { CheckCircle2, Clock, AlertTriangle, ExternalLink } from "lucide-react";

interface PositionsTableProps {
  positions: Position[];
  loading?: boolean;
}

export default function PositionsTable({
  positions,
  loading,
}: PositionsTableProps) {
  return (
    <div className="terminal-card rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-[#231f4b] flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-100 flex items-center space-x-2">
            <span>Active Paper Positions</span>
            <span className="px-2 py-0.5 rounded-full text-[10px] bg-purple-900/40 text-purple-300 font-mono border border-purple-700/40">
              {positions.length} Open
            </span>
          </h2>
          <p className="text-xs text-zinc-400 mt-0.5">
            Solana Trailing Stop Strategy &bull; Stop trigger locked 15% below
            post-activation peak &bull; Jito MEV protection
          </p>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-[#0b0a1a] text-zinc-400 uppercase tracking-wider font-mono border-b border-[#231f4b]">
            <tr>
              <th className="py-3 px-4">Token Address</th>
              <th className="py-3 px-4">Entry Price</th>
              <th className="py-3 px-4">Allocation</th>
              <th className="py-3 px-4">Peak (Post-Activation)</th>
              <th className="py-3 px-4">Trailing Stop (-15%)</th>
              <th className="py-3 px-4">Opened</th>
              <th className="py-3 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1e1a3f] font-mono">
            {loading ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-zinc-500">
                  Loading position states...
                </td>
              </tr>
            ) : positions.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-zinc-500">
                  <div className="flex flex-col items-center justify-center space-y-2">
                    <Clock className="w-6 h-6 text-zinc-600" />
                    <span>No active paper positions open currently.</span>
                    <span className="text-[11px] text-zinc-600">
                      The bot will open up to 3 simultaneous positions when
                      candidate tokens pass opportunity & risk checks.
                    </span>
                  </div>
                </td>
              </tr>
            ) : (
              positions.map((pos) => {
                const peakPrice = pos.highest_price || pos.actual_entry_price;
                const stopLossPrice = peakPrice * 0.85;
                const peakGainPct =
                  ((peakPrice - pos.actual_entry_price) /
                    pos.actual_entry_price) *
                  100;

                return (
                  <tr
                    key={pos.token}
                    className="hover:bg-purple-950/20 transition-colors"
                  >
                    <td className="py-3 px-4 font-semibold text-purple-300">
                      <div className="flex items-center space-x-2">
                        <span>{truncateAddress(pos.token, 6)}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-zinc-200">
                      {formatCurrency(pos.entry_price, 6)}
                    </td>
                    <td className="py-3 px-4 text-zinc-200">
                      {formatCurrency(pos.trade_size)}
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center space-x-2">
                        <span className="text-zinc-200 font-medium">
                          {formatCurrency(peakPrice, 6)}
                        </span>
                        {peakGainPct > 0.5 && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-400 border border-emerald-800">
                            +{peakGainPct.toFixed(1)}%
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-rose-400 font-semibold">
                      {formatCurrency(stopLossPrice, 6)}
                    </td>
                    <td className="py-3 px-4 text-zinc-400">
                      {formatTimeAgo(pos.opened_at)}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <a
                        href={`https://dexscreener.com/solana/${pos.token}`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center space-x-1 text-purple-400 hover:text-purple-300"
                      >
                        <span>Chart</span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
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

'use client';

import { DollarSign, TrendingUp, ShieldCheck, Activity } from 'lucide-react';
import { BotStatus, PaperTrade } from '@/lib/types';
import { formatCurrency, formatPercent } from '@/lib/formatters';

interface StatCardsProps {
  status: BotStatus | null;
  liveTrades?: PaperTrade[];
}

export default function StatCards({ status, liveTrades = [] }: StatCardsProps) {
  const balance = status?.balanceUsd ?? 50.0;
  const initial = status?.initialBalanceUsd ?? 50.0;
  const pnl = balance - initial;
  const pnlPct = initial > 0 ? (pnl / initial) * 100 : 0.0;

  // Calculate stats strictly from THIS live 7-day trial run
  const totalClosed = liveTrades.length;
  const wins = liveTrades.filter((t) => Number(t.pnl) > 0).length;
  const losses = liveTrades.filter((t) => Number(t.pnl) <= 0).length;
  const winRate = totalClosed > 0 ? (wins / totalClosed) * 100 : 0;

  const stats = [
    {
      title: 'Simulated Wallet Balance',
      value: formatCurrency(balance),
      subtext: `${pnl >= 0 ? '+' : ''}${formatCurrency(pnl)} net P/L`,
      subtextColor: pnl >= 0 ? 'text-emerald-400' : 'text-rose-400',
      icon: DollarSign,
      glow: 'glow-purple',
      badge: 'Active Balance',
    },
    {
      title: 'Current Return',
      value: formatPercent(pnlPct),
      subtext: `From $${initial.toFixed(2)} base capital`,
      subtextColor: pnlPct >= 0 ? 'text-emerald-400' : 'text-rose-400',
      icon: TrendingUp,
      glow: pnlPct >= 0 ? 'glow-green' : 'glow-red',
      badge: 'Compounded',
    },
    {
      title: 'Live Test Win Rate',
      value: totalClosed > 0 ? `${winRate.toFixed(1)}%` : 'Fresh Trial',
      subtext:
        totalClosed > 0
          ? `${wins}W / ${losses}L (${totalClosed} closed)`
          : `0 closed • ${status?.openPositionsCount ?? 0} active`,
      subtextColor: 'text-zinc-400',
      icon: ShieldCheck,
      glow: 'glow-purple',
      badge: '7-Day Run',
    },
    {
      title: 'Active Open Positions',
      value: `${status?.openPositionsCount ?? 0} / ${status?.maxOpenPositions ?? 3}`,
      subtext: '$4.17 / slot • 15% dynamic stop',
      subtextColor: 'text-zinc-400',
      icon: Activity,
      glow: 'glow-purple',
      badge: 'Live State',
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {stats.map((stat, i) => {
        const Icon = stat.icon;
        return (
          <div
            key={i}
            className={`terminal-card rounded-xl p-5 relative overflow-hidden transition-all duration-300 hover:border-purple-600/40`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-zinc-400 uppercase tracking-wider font-mono">
                {stat.title}
              </span>
              <div className="flex items-center space-x-1.5">
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1e1a3f] text-purple-300 border border-[#2e265c]">
                  {stat.badge}
                </span>
                <div className="p-2 rounded-lg bg-purple-950/40 border border-purple-800/30 text-purple-400">
                  <Icon className="w-4 h-4" />
                </div>
              </div>
            </div>

            <div className="mt-4">
              <div className="text-2xl font-bold font-mono tracking-tight text-white">
                {stat.value}
              </div>
              <div className={`text-xs mt-1 font-mono ${stat.subtextColor}`}>
                {stat.subtext}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

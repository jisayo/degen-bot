'use client';

import { DollarSign, TrendingUp, ShieldCheck, Activity } from 'lucide-react';
import { BotStatus } from '@/lib/types';
import { formatCurrency, formatPercent } from '@/lib/formatters';

interface StatCardsProps {
  status: BotStatus | null;
  winRate?: number;
  totalTrades?: number;
}

export default function StatCards({ status, winRate = 54.94, totalTrades = 162 }: StatCardsProps) {
  const balance = status?.balanceUsd ?? 50.0;
  const initial = status?.initialBalanceUsd ?? 50.0;
  const pnl = balance - initial;
  const pnlPct = (pnl / initial) * 100;

  const stats = [
    {
      title: 'Simulated Wallet Balance',
      value: formatCurrency(balance),
      subtext: `${pnl >= 0 ? '+' : ''}${formatCurrency(pnl)} net P/L`,
      subtextColor: pnl >= 0 ? 'text-emerald-400' : 'text-rose-400',
      icon: DollarSign,
      glow: 'glow-purple',
      badge: '1 Wallet Model',
    },
    {
      title: 'Current Return',
      value: formatPercent(pnlPct),
      subtext: 'From $50.00 base capital',
      subtextColor: 'text-zinc-400',
      icon: TrendingUp,
      glow: pnlPct >= 0 ? 'glow-green' : 'glow-red',
      badge: 'Compounded',
    },
    {
      title: 'Backtest Win Rate',
      value: `${winRate.toFixed(1)}%`,
      subtext: `${totalTrades} single-entry trades executed`,
      subtextColor: 'text-zinc-400',
      icon: ShieldCheck,
      glow: 'glow-purple',
      badge: 'Audited Cohort',
    },
    {
      title: 'Active Open Positions',
      value: `${status?.openPositionsCount ?? 0} / ${status?.maxOpenPositions ?? 1}`,
      subtext: 'Risk guard: 20% max size',
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
            className="terminal-card rounded-xl p-5 relative overflow-hidden transition-all duration-300 hover:border-purple-600/60"
          >
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-medium text-zinc-400 uppercase tracking-wider">{stat.title}</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-purple-950/60 text-purple-300 border border-purple-800/40">
                {stat.badge}
              </span>
            </div>
            <div className="flex items-baseline justify-between">
              <div>
                <div className="text-2xl font-bold font-mono tracking-tight text-white mb-1">{stat.value}</div>
                <div className={`text-xs font-mono font-medium ${stat.subtextColor}`}>{stat.subtext}</div>
              </div>
              <div className="w-10 h-10 rounded-lg bg-purple-900/20 border border-purple-700/30 flex items-center justify-center">
                <Icon className="w-5 h-5 text-purple-400" />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

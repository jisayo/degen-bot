'use client';

import { Shield, Clock, Droplets, TrendingUp, Target, Zap, DollarSign, Lock } from 'lucide-react';

export default function StrategyConditionsCard() {
  const conditions = [
    {
      title: 'Token Age Window',
      value: '1 – 120 Minutes',
      description: 'Filters out uninitialized pairs and inactive dead legacy tokens.',
      icon: Clock,
      color: 'text-purple-400',
      badge: 'Active Gate',
    },
    {
      title: 'Minimum Pool Liquidity',
      value: '≥ $20,000 USD',
      description: 'Depth floor to filter out shallow sniper-dumped pools and reduce slippage.',
      icon: Droplets,
      color: 'text-blue-400',
      badge: 'Depth Floor',
    },
    {
      title: 'Liquidity / MC Ratio',
      value: '≥ 15% of MC',
      description: 'Standard health ratio for active Solana Raydium memecoin pools.',
      icon: DollarSign,
      color: 'text-cyan-400',
      badge: 'Solana Ratio',
    },
    {
      title: 'Bullish Order Flow',
      value: '≥ 60% Buy Volume',
      description: 'Minimum 60:40 buy-to-sell ratio ensuring positive market momentum.',
      icon: TrendingUp,
      color: 'text-emerald-400',
      badge: 'Momentum Gate',
    },
    {
      title: 'RugCheck Contract Audit',
      value: 'Risk Score: LOW',
      description: 'Mint revoked, freeze disabled, LP tokens locked/burned.',
      icon: Shield,
      color: 'text-emerald-400',
      badge: 'Safety Check',
    },
    {
      title: 'Solana Trailing Ratchet',
      value: 'TP (+50%/+100%) & 15% Trail',
      description: 'Staged profit banking (+50%/+100% sell 35% each). 25% noise buffer, trailing 30% moonbag.',
      icon: Target,
      color: 'text-amber-400',
      badge: 'Dynamic Exit',
    },
    {
      title: 'MEV Sandwich Protection',
      value: 'Jito Private Bundles',
      description: 'Bypasses public mempool to prevent frontrunning and sandwich bots.',
      icon: Zap,
      color: 'text-indigo-400',
      badge: 'Private Route',
    },
    {
      title: 'Risk Guard & Slot Limit',
      value: '$4.17 / Slot (Max 3)',
      description: 'Allocates 8.33% ($4.17) per trade, capping total risk at 25% ($12.50) across 3 slots.',
      icon: Lock,
      color: 'text-rose-400',
      badge: 'Risk Guard',
    },
  ];

  return (
    <div className="terminal-card rounded-xl overflow-hidden">
      <div className="px-5 py-4 border-b border-[#231f4b] flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-100 flex items-center space-x-2">
            <Target className="w-4 h-4 text-purple-400" />
            <span>Active Strategy & Entry Conditions</span>
            <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-950/60 text-emerald-400 font-mono border border-emerald-800">
              Live Rules
            </span>
          </h2>
          <p className="text-xs text-zinc-400 mt-0.5">
            Pre-trade safety gates and execution criteria enforced on every scanned Solana memecoin.
          </p>
        </div>
      </div>

      <div className="p-5 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {conditions.map((item, idx) => {
          const Icon = item.icon;
          return (
            <div
              key={idx}
              className="p-3.5 rounded-xl bg-[#0b0a1a] border border-[#231f4b] hover:border-purple-800/40 transition-all flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className={`p-1.5 rounded-lg bg-purple-950/40 border border-purple-800/30 ${item.color}`}>
                    <Icon className="w-4 h-4" />
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#161331] text-zinc-400 border border-[#2e265c]">
                    {item.badge}
                  </span>
                </div>
                <h3 className="text-xs font-semibold text-zinc-300">{item.title}</h3>
                <div className="text-sm font-bold font-mono text-white mt-0.5">{item.value}</div>
              </div>
              <p className="text-[11px] text-zinc-400 mt-2 leading-relaxed">
                {item.description}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

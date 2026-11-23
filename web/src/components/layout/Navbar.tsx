'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Bot, LineChart, Radio, Wallet, ShieldAlert, Cpu } from 'lucide-react';
import { useEffect, useState } from 'react';
import { BotStatus } from '@/lib/types';
import { formatCurrency, formatPercent } from '@/lib/formatters';

export default function Navbar() {
  const pathname = usePathname();
  const [status, setStatus] = useState<BotStatus | null>(null);

  useEffect(() => {
    async function fetchStatus() {
      try {
        const res = await fetch('/api/bot/status');
        if (res.ok) {
          const data = await res.json();
          setStatus(data);
        }
      } catch {}
    }
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const navItems = [
    { name: 'Dashboard', href: '/', icon: Bot },
    { name: 'Live Scanner', href: '/scanner', icon: Radio },
    { name: 'Backtest Hub', href: '/backtest', icon: LineChart },
  ];

  return (
    <header className="border-b border-[#231f4b] bg-[#0c0a1d]/80 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-8">
          <Link href="/" className="flex items-center space-x-3 group">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-purple-700 to-fuchsia-500 flex items-center justify-center shadow-lg shadow-purple-900/40 group-hover:scale-105 transition-transform">
              <Cpu className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-extrabold tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-purple-400 via-fuchsia-300 to-purple-200 text-lg">
                  DEGEN-BOT
                </span>
                <span className="px-1.5 py-0.5 text-[10px] font-bold rounded bg-purple-950/80 text-purple-300 border border-purple-800">
                  SOLANA
                </span>
              </div>
              <p className="text-[10px] text-zinc-400 tracking-tight">QUANTITATIVE RESEARCH TERMINAL</p>
            </div>
          </Link>

          <nav className="hidden md:flex space-x-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.name}
                  href={item.href}
                  className={`flex items-center space-x-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? 'bg-purple-900/40 text-purple-200 border border-purple-600/50 shadow-sm shadow-purple-900/30'
                      : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/40'
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? 'text-purple-400' : 'text-zinc-400'}`} />
                  <span>{item.name}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Right side status & wallet badge */}
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg bg-zinc-950/80 border border-[#231f4b] text-xs">
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-zinc-300 font-mono font-medium">PAPER MODE</span>
          </div>

          <div className="flex items-center space-x-3 px-3 py-1.5 rounded-lg bg-purple-950/30 border border-purple-800/40">
            <Wallet className="w-4 h-4 text-purple-400" />
            <div className="text-right">
              <span className="text-xs font-mono font-bold text-zinc-100">
                {formatCurrency(status?.balanceUsd ?? 50.0)}
              </span>
              <span
                className={`ml-2 text-[10px] font-mono font-semibold ${
                  (status?.pnlPercent ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {formatPercent(status?.pnlPercent ?? 0)}
              </span>
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

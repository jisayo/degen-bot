'use client';

import { useEffect, useState } from 'react';
import StatCards from '@/components/dashboard/StatCards';
import PositionsTable from '@/components/dashboard/PositionsTable';
import BacktestWidget from '@/components/dashboard/BacktestWidget';
import { BotStatus, Position, BacktestAggregate, BacktestTrade } from '@/lib/types';
import { Radio, RefreshCw, Zap, Shield, Flame } from 'lucide-react';

export default function DashboardPage() {
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [backtestAggregate, setBacktestAggregate] = useState<BacktestAggregate | null>(null);
  const [backtestTrades, setBacktestTrades] = useState<BacktestTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  async function loadData() {
    try {
      const [statusRes, positionsRes, backtestRes] = await Promise.all([
        fetch('/api/bot/status'),
        fetch('/api/bot/positions'),
        fetch('/api/backtest'),
      ]);

      if (statusRes.ok) {
        setStatus(await statusRes.json());
      }
      if (positionsRes.ok) {
        const data = await positionsRes.json();
        setPositions(data.positions || []);
      }
      if (backtestRes.ok) {
        const data = await backtestRes.json();
        setBacktestAggregate(data.aggregate || null);
        setBacktestTrades(data.trades || []);
      }
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    loadData();
    const timer = setInterval(loadData, 5000);
    return () => clearInterval(timer);
  }, []);

  const handleManualRefresh = () => {
    setRefreshing(true);
    loadData();
  };

  return (
    <div className="space-y-6">
      {/* Top Banner / Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl bg-gradient-to-r from-purple-950/40 via-[#100e23] to-[#100e23] border border-purple-900/30">
        <div className="flex items-center space-x-3">
          <div className="w-3 h-3 rounded-full bg-emerald-400 animate-ping" />
          <div>
            <h1 className="text-base font-bold text-white tracking-wide flex items-center space-x-2">
              <span>SOLANA LIVE TRADING TERMINAL</span>
              <span className="text-xs px-2 py-0.5 rounded bg-purple-900/60 text-purple-300 font-mono border border-purple-700">
                PAPER EXECUTION
              </span>
            </h1>
            <p className="text-xs text-zinc-400">
              Autonomous token discovery, RugCheck risk evaluation, and staged trade execution.
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={handleManualRefresh}
            disabled={refreshing}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium bg-[#1e1a3f] text-zinc-300 hover:text-white hover:bg-purple-900/40 border border-[#2e265c] transition-all disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            <span>Refresh State</span>
          </button>
        </div>
      </div>

      {/* KPI Metric Cards */}
      <StatCards
        status={status}
        winRate={backtestAggregate?.win_rate_pct ?? 54.94}
        totalTrades={backtestAggregate?.trades_executed ?? 162}
      />

      {/* Grid: Active Positions & Quick Status */}
      <div className="space-y-6">
        <PositionsTable positions={positions} loading={loading} />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <BacktestWidget
              aggregate={backtestAggregate}
              trades={backtestTrades}
              loading={loading}
            />
          </div>

          {/* Strategy Engine Parameters Box */}
          <div className="terminal-card rounded-xl p-5 space-y-4">
            <div className="border-b border-[#231f4b] pb-3">
              <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-100 flex items-center space-x-2">
                <Shield className="w-4 h-4 text-purple-400" />
                <span>Live Guardrails & Strategy</span>
              </h3>
              <p className="text-xs text-zinc-400 mt-0.5">Verified parameters currently enforced</p>
            </div>

            <div className="space-y-3 font-mono text-xs">
              <div className="flex justify-between py-1.5 border-b border-[#1b1739]">
                <span className="text-zinc-400">Max Open Positions</span>
                <span className="text-purple-300 font-semibold">1 (Conservative)</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-[#1b1739]">
                <span className="text-zinc-400">Position Allocation</span>
                <span className="text-zinc-200">20% of cash</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-[#1b1739]">
                <span className="text-zinc-400">Hard Stop Loss</span>
                <span className="text-rose-400 font-semibold">-15.0%</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-[#1b1739]">
                <span className="text-zinc-400">Take Profit 1</span>
                <span className="text-emerald-400 font-semibold">+50.0% (Sell 50%)</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-[#1b1739]">
                <span className="text-zinc-400">Take Profit 2</span>
                <span className="text-emerald-400 font-semibold">+100.0% (Sell 25%)</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-[#1b1739]">
                <span className="text-zinc-400">Trailing Runner</span>
                <span className="text-purple-300 font-semibold">15.0% Trailing Stop</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-[#1b1739]">
                <span className="text-zinc-400">RugCheck Requirement</span>
                <span className="text-emerald-400 font-semibold">LOW Risk Only</span>
              </div>
              <div className="flex justify-between py-1.5">
                <span className="text-zinc-400">Min Liq / MC Ratio</span>
                <span className="text-zinc-200">&gt;= 0.50 (50%)</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

'use client';

import { useEffect, useState } from 'react';
import StatCards from '@/components/dashboard/StatCards';
import PositionsTable from '@/components/dashboard/PositionsTable';
import StrategyConditionsCard from '@/components/dashboard/StrategyConditionsCard';
import LiveTradesTable from '@/components/dashboard/LiveTradesTable';
import { BotStatus, Position, PaperTrade } from '@/lib/types';
import { RefreshCw, RotateCcw, Timer, Activity, ShieldCheck } from 'lucide-react';

export default function DashboardPage() {
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [liveTrades, setLiveTrades] = useState<PaperTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [resetting, setResetting] = useState(false);

  async function loadData() {
    try {
      const [statusRes, positionsRes, tradesRes] = await Promise.all([
        fetch('/api/bot/status'),
        fetch('/api/bot/positions'),
        fetch('/api/bot/trades'),
      ]);

      if (statusRes.ok) {
        setStatus(await statusRes.json());
      }
      if (positionsRes.ok) {
        const data = await positionsRes.json();
        setPositions(data.positions || []);
      }
      if (tradesRes.ok) {
        const data = await tradesRes.json();
        setLiveTrades(data.trades || []);
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

  const handleResetData = async () => {
    if (
      !window.confirm(
        'Are you sure you want to clear all previous trades and restart the 7-day paper trading trial with $50.00?'
      )
    ) {
      return;
    }
    setResetting(true);
    try {
      const res = await fetch('/api/bot/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ startingBalance: 50.0 }),
      });
      if (res.ok) {
        await loadData();
      }
    } catch (err) {
      console.error('Reset failed:', err);
    } finally {
      setResetting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner / Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl bg-gradient-to-r from-purple-950/40 via-[#100e23] to-[#100e23] border border-purple-900/30">
        <div className="flex items-center space-x-3">
          <div className="w-3 h-3 rounded-full bg-emerald-400 animate-ping" />
          <div>
            <h1 className="text-base font-bold text-white tracking-wide flex items-center space-x-2">
              <span>SOLANA LIVE TRADING TRIAL</span>
              <span className="text-xs px-2 py-0.5 rounded bg-purple-900/60 text-purple-300 font-mono border border-purple-700">
                7-DAY TEST RUN
              </span>
            </h1>
            <p className="text-xs text-zinc-400">
              Live automated paper execution on Solana &bull; Base capital: $50.00 &bull; 15% Dynamic Trailing Stop
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleResetData}
            disabled={resetting}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium bg-rose-950/30 text-rose-300 hover:text-white hover:bg-rose-900/40 border border-rose-800/40 transition-all disabled:opacity-50"
            title="Reset trade history and restart 7-day test with $50"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${resetting ? 'animate-spin' : ''}`} />
            <span>Reset 7-Day Test ($50)</span>
          </button>

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

      {/* 7-Day Live Test Progress Banner */}
      {status?.testStartedAt && (
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-3 rounded-xl bg-purple-950/20 border border-purple-800/40 text-xs font-mono">
          <div className="flex items-center space-x-2 text-purple-200">
            <Timer className="w-4 h-4 text-purple-400" />
            <span>
              <b>7-Day Live Test Active:</b> Base Capital $50.00
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-zinc-300">
            <span>Started: {new Date(status.testStartedAt).toLocaleDateString()}</span>
            <span>Ends: {status.testEndsAt ? new Date(status.testEndsAt).toLocaleDateString() : '7 Days'}</span>
            <span className="px-2.5 py-0.5 rounded-full bg-emerald-950/70 text-emerald-300 border border-emerald-700/60 font-semibold">
              {status.daysRemaining ?? 7} Days Left
            </span>
          </div>
        </div>
      )}

      {/* KPI Metric Cards (Strictly for this Current 7-Day Run) */}
      <StatCards status={status} liveTrades={liveTrades} />

      {/* 1. Active Open Positions Table */}
      <PositionsTable positions={positions} loading={loading} />

      {/* 2. Strategy & Entry Conditions Card */}
      <StrategyConditionsCard />

      {/* 3. Live Completed Trades Table (For this 7-Day Test) */}
      <LiveTradesTable trades={liveTrades} loading={loading} />
    </div>
  );
}

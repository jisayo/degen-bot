import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const rootDir = path.resolve(process.cwd(), '..');
    const stateFile = path.join(rootDir, 'data', 'paper_state.json');
    const positionsFile = path.join(rootDir, 'data', 'open_positions.json');

    let balance = 50.0;
    let initial = 50.0;
    let testStartedAt: string | null = null;
    let testEndsAt: string | null = null;
    let daysRemaining: number | null = null;
    let openPositionsCount = 0;

    if (fs.existsSync(stateFile)) {
      try {
        const state = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
        balance = Number(state.balance) || 50.0;
        initial = Number(state.initial_balance) || 50.0;
        if (state.test_started_at) {
          testStartedAt = state.test_started_at;
          const startedMs = new Date(state.test_started_at).getTime();
          const durationDays = Number(state.test_duration_days) || 7;
          const endsMs = startedMs + durationDays * 24 * 60 * 60 * 1000;
          testEndsAt = new Date(endsMs).toISOString();
          daysRemaining = Math.max(0, Math.ceil((endsMs - Date.now()) / (24 * 60 * 60 * 1000)));
        }
      } catch {}
    }

    if (fs.existsSync(positionsFile)) {
      try {
        const positions = JSON.parse(fs.readFileSync(positionsFile, 'utf8'));
        if (Array.isArray(positions)) {
          openPositionsCount = positions.length;
        }
      } catch {}
    }

    const pnl = balance - initial;
    const pnlPct = initial > 0 ? (pnl / initial) * 100 : 0;

    return NextResponse.json({
      online: true,
      mode: 'PAPER',
      walletAddress: 'DEMO-SOL-PAPER-WALLET',
      balanceUsd: balance,
      initialBalanceUsd: initial,
      totalPnlUsd: pnl,
      pnlPercent: pnlPct,
      openPositionsCount,
      maxOpenPositions: 3,
      testStartedAt,
      testEndsAt,
      daysRemaining,
      lastScanTime: new Date().toISOString(),
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

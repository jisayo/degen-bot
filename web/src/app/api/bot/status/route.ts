import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET() {
  try {
    const rootDir = path.resolve(process.cwd(), '..');
    const stateFile = path.join(rootDir, 'data', 'paper_state.json');
    const positionsFile = path.join(rootDir, 'data', 'open_positions.json');

    let balance = 50.0;
    let openPositionsCount = 0;

    if (fs.existsSync(stateFile)) {
      try {
        const state = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
        balance = Number(state.balance) || 50.0;
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

    const initial = 50.0;
    const pnl = balance - initial;
    const pnlPct = (pnl / initial) * 100;

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
      lastScanTime: new Date().toISOString(),
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

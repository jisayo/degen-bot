import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export const dynamic = 'force-dynamic';

export async function POST(request: Request) {
  try {
    const rootDir = path.resolve(process.cwd(), '..');
    const dataDir = path.join(rootDir, 'data');
    const stateFile = path.join(dataDir, 'paper_state.json');
    const positionsFile = path.join(dataDir, 'open_positions.json');
    const tradesFile = path.join(dataDir, 'paper_trades.csv');

    if (!fs.existsSync(dataDir)) {
      fs.mkdirSync(dataDir, { recursive: true });
    }

    let startingBalance = 50.0;
    try {
      const body = await request.json();
      if (body && typeof body.startingBalance === 'number' && body.startingBalance > 0) {
        startingBalance = body.startingBalance;
      }
    } catch {
      // Use default $50.00
    }

    const now = new Date().toISOString();

    // 1. Reset paper state with 7-day test duration
    const state = {
      balance: startingBalance,
      initial_balance: startingBalance,
      test_started_at: now,
      test_duration_days: 7,
    };
    fs.writeFileSync(stateFile, JSON.stringify(state, null, 2), 'utf8');

    // 2. Clear open positions
    fs.writeFileSync(positionsFile, JSON.stringify([], null, 2), 'utf8');

    // 3. Clear trade history (keep CSV headers)
    const csvHeader = 'timestamp,token,entry_price,exit_price,trade_size,fees,slippage,pnl,balance,reason\n';
    fs.writeFileSync(tradesFile, csvHeader, 'utf8');

    return NextResponse.json({
      success: true,
      message: `All previous trading data cleared. Starting fresh 7-day test with $${startingBalance.toFixed(2)}.`,
      state,
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}

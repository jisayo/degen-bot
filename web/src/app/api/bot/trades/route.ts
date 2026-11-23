import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET() {
  try {
    const rootDir = path.resolve(process.cwd(), '..');
    const csvFile = path.join(rootDir, 'data', 'paper_trades.csv');

    if (!fs.existsSync(csvFile)) {
      return NextResponse.json({ trades: [] });
    }

    const content = fs.readFileSync(csvFile, 'utf8');
    const lines = content.split('\n').map((l) => l.trim()).filter(Boolean);
    if (lines.length <= 1) {
      return NextResponse.json({ trades: [] });
    }

    const headers = lines[0].split(',').map((h) => h.trim());
    const trades = lines.slice(1).map((line) => {
      const values = line.split(',').map((v) => v.trim());
      const row: Record<string, string | number> = {};
      headers.forEach((h, idx) => {
        const val = values[idx] || '';
        const num = Number(val);
        row[h] = !isNaN(num) && val !== '' ? num : val;
      });
      return row;
    }).reverse(); // Most recent first

    return NextResponse.json({ trades });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: message, trades: [] }, { status: 500 });
  }
}

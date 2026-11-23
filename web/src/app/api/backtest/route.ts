import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET() {
  try {
    const rootDir = path.resolve(process.cwd(), '..');
    const backtestFile = path.join(
      rootDir,
      'results',
      'backtest',
      'november_2026',
      'clean_cohort',
      'single_entry_results.json'
    );

    if (!fs.existsSync(backtestFile)) {
      return NextResponse.json({ error: 'No backtest data found' }, { status: 404 });
    }

    const content = fs.readFileSync(backtestFile, 'utf8');
    const data = JSON.parse(content);

    return NextResponse.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

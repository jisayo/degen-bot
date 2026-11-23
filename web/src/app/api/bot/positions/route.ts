import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET() {
  try {
    const rootDir = path.resolve(process.cwd(), '..');
    const positionsFile = path.join(rootDir, 'data', 'open_positions.json');

    if (!fs.existsSync(positionsFile)) {
      return NextResponse.json({ positions: [] });
    }

    const content = fs.readFileSync(positionsFile, 'utf8');
    const positions = JSON.parse(content);

    return NextResponse.json({ positions: Array.isArray(positions) ? positions : [] });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ error: message, positions: [] }, { status: 500 });
  }
}

export interface BotStatus {
  online: boolean;
  mode: 'PAPER' | 'LIVE_DISABLED';
  walletAddress: string;
  balanceUsd: number;
  initialBalanceUsd: number;
  totalPnlUsd: number;
  pnlPercent: number;
  openPositionsCount: number;
  maxOpenPositions: number;
  lastScanTime?: string;
}

export interface Position {
  token: string;
  name?: string;
  symbol?: string;
  entry_price: number;
  actual_entry_price: number;
  highest_price: number;
  current_price?: number;
  quantity: number;
  original_quantity: number;
  trade_size: number;
  entry_fee: number;
  unrealized_pnl?: number;
  unrealized_pnl_pct?: number;
  first_take_profit_done: boolean;
  second_take_profit_done: boolean;
  trailing_stop_active: boolean;
  opened_at: string;
}

export interface PaperTrade {
  timestamp: string;
  token: string;
  entry_price: number;
  exit_price: number;
  trade_size: number;
  fees: number;
  slippage: number;
  pnl: number;
  balance: number;
  reason: string;
}

export interface ScannedToken {
  mint: string;
  name: string;
  symbol: string;
  age_minutes: number;
  price_usd: number;
  liquidity_usd: number;
  market_cap_usd: number;
  liquidity_to_mc_ratio: number;
  volume_1h_usd: number;
  buys_1h: number;
  sells_1h: number;
  risk_level: 'LOW' | 'WARN' | 'DANGER';
  risk_score: number;
  opportunity_score: number;
  is_eligible: boolean;
  pair_url: string;
  scanned_at: string;
}

export interface BacktestTrade {
  pool: string;
  entry_time: number;
  exit_time: number;
  entry_price: number;
  exit_price: number;
  allocation: number;
  entry_fee: number;
  exit_fee: number;
  net_pnl: number;
  wallet_cash: number;
  exit_reason: string;
  post_activation_peak?: number;
  peak_gain_pct?: number;
}

export interface BacktestAggregate {
  mode: string;
  starting_balance: number;
  final_balance: number;
  total_net_pnl: number;
  return_pct: number;
  max_drawdown_pct: number;
  pools_found: number;
  trades_executed: number;
  trades_skipped: number;
  wins: number;
  losses: number;
  win_rate_pct: number;
  mean_trade_pnl: number;
  median_trade_pnl: number;
  exit_reasons: Record<string, number>;
}

export interface BacktestData {
  aggregate: BacktestAggregate;
  trades: BacktestTrade[];
}

export function formatCurrency(value: number | undefined | null, decimals = 2): string {
  if (value === undefined || value === null || isNaN(value)) return '$0.00';
  if (Math.abs(value) < 0.0001 && value !== 0) {
    return `$${value.toExponential(4)}`;
  }
  if (Math.abs(value) < 0.01 && value !== 0) {
    return `$${value.toFixed(6)}`;
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

export function formatPercent(value: number | undefined | null): string {
  if (value === undefined || value === null || isNaN(value)) return '0.00%';
  const prefix = value > 0 ? '+' : '';
  return `${prefix}${value.toFixed(2)}%`;
}

export function formatNumber(value: number | undefined | null): string {
  if (value === undefined || value === null || isNaN(value)) return '0';
  return new Intl.NumberFormat('en-US', { notation: 'compact' }).format(value);
}

export function truncateAddress(address: string, chars = 4): string {
  if (!address || address.length < chars * 2 + 2) return address;
  return `${address.slice(0, chars)}...${address.slice(-chars)}`;
}

export function formatTimeAgo(isoString: string | number): string {
  const timestamp = typeof isoString === 'number' ? isoString * 1000 : new Date(isoString).getTime();
  const diffSeconds = Math.floor((Date.now() - timestamp) / 1000);

  if (diffSeconds < 60) return `${diffSeconds}s ago`;
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

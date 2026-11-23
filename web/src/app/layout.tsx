import type { Metadata } from 'next';
import './globals.css';
import Navbar from '@/components/layout/Navbar';

export const metadata: Metadata = {
  title: 'DEGEN-BOT — Solana Quantitative Trading Terminal',
  description: 'Autonomous token discovery, RugCheck risk screening, and staged paper trading on Solana',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="antialiased bg-[#080711] text-zinc-100 min-h-screen flex flex-col">
        <Navbar />
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {children}
        </main>
        <footer className="border-t border-[#1e1a3f] py-4 bg-[#0a0818]/60 text-center text-xs text-zinc-500 font-mono">
          DEGEN-BOT RESEARCH TERMINAL &bull; NON-CUSTODIAL &bull; NO LIVE TRADES ARE EXECUTED
        </footer>
      </body>
    </html>
  );
}

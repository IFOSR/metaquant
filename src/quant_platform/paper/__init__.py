"""Paper trading (仿真) platform: long-running simulated accounts.

Backtests answer "did this strategy make money historically"; paper accounts
answer "does the trading pipeline work" — incremental data, full order
lifecycle against a simulated exchange, persistent ledger. See
``docs/plans/2026-08-22-backtest-paper-platform-design.md``.
"""

"""因子回测服务（策略台面 V1）。

从已晋级因子的计算产物（因子值）与正式快照行情（日频 OHLCV）出发，
用 NautilusTrader 事件驱动引擎跑单因子方向性回测，产出确定性的净值曲线、
绩效指标与内容寻址结果指纹（``backtest_hash``）。

本版边界（与 UI 披露一致）：
- 期货日频、毛回测（不扣手续费/滑点/保证金占用收益）
- 仓位桥规则：T 日因子值 > 0 → T+1 日起持有 +lot_size 手，< 0 → -lot_size 手，
  否则平仓（对齐 decision_clock T_CLOSE+30m / T+1_OPEN 的日频近似，
  严格使用早于当根 bar 的因子值，避免前视）
"""

from .service import (
    BacktestMetrics,
    BacktestPosition,
    BacktestResult,
    BacktestTrade,
    run_factor_backtest,
)

__all__ = [
    "BacktestMetrics",
    "BacktestPosition",
    "BacktestResult",
    "BacktestTrade",
    "run_factor_backtest",
]

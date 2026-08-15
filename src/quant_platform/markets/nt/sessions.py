"""交易时段规则（G18 P0）。

NautilusTrader 无通用可自定义的交易时段概念（只有外汇 ForexSession），
中国 A 股/期货的时段规则由本模块定义，供数据层过滤与 ``trading_date``
归属使用。数据驱动回测时，bar 时间戳本身就是交易时间的体现。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True, slots=True)
class TradingSession:
    open: time
    close: time

    def __post_init__(self) -> None:
        if self.close <= self.open:
            raise ValueError("close must be after open")

    def contains(self, moment: time) -> bool:
        return self.open <= moment < self.close


# A 股：上午 09:30-11:30，下午 13:00-15:00。
A_SHARE_SESSIONS: tuple[TradingSession, ...] = (
    TradingSession(time(9, 30), time(11, 30)),
    TradingSession(time(13, 0), time(15, 0)),
)

# 商品期货日盘（通用，个别品种时段略有差异，按品种可覆盖）。
FUTURES_DAY_SESSIONS: tuple[TradingSession, ...] = (
    TradingSession(time(9, 0), time(10, 15)),
    TradingSession(time(10, 30), time(11, 30)),
    TradingSession(time(13, 30), time(15, 0)),
)

# 商品期货夜盘（通用 21:00-23:00；部分品种到次日 01:00/02:30，按品种可覆盖）。
FUTURES_NIGHT_SESSIONS: tuple[TradingSession, ...] = (
    TradingSession(time(21, 0), time(23, 0)),
)


def is_night_session(moment: datetime) -> bool:
    """判断时刻是否属于夜盘（>= 20:00，用于 trading_date 归属）。"""
    return moment.hour >= 20


def in_sessions(moment: datetime, sessions: tuple[TradingSession, ...]) -> bool:
    local = moment.astimezone(SHANGHAI)
    return any(session.contains(local.time()) for session in sessions)

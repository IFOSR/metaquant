from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")


class AsiaShanghaiClock:
    timezone = SHANGHAI

    @classmethod
    def localize(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=cls.timezone)
        return value.astimezone(cls.timezone)


@dataclass(frozen=True, slots=True)
class AShareClockEvents:
    decision_at: datetime
    trade_at: datetime


@dataclass(frozen=True, slots=True)
class CnAShareClock:
    decision_time: time = time(15, 30)
    trade_time: time = time(9, 35)

    def events(self, trade_date: date, next_trade_date: date) -> AShareClockEvents:
        if next_trade_date <= trade_date:
            raise ValueError("next_trade_date must follow trade_date")
        return AShareClockEvents(
            decision_at=datetime.combine(
                trade_date,
                self.decision_time,
                tzinfo=SHANGHAI,
            ),
            trade_at=datetime.combine(
                next_trade_date,
                self.trade_time,
                tzinfo=SHANGHAI,
            ),
        )


@dataclass(frozen=True, slots=True)
class FuturesSessionTemplate:
    product: str
    night_start: time
    night_end: time
    settlement_at: time

    def __post_init__(self) -> None:
        if not self.product or self.product.strip() != self.product:
            raise ValueError("product must be a normalized identifier")
        if self.night_start == self.night_end:
            raise ValueError("night session must have non-zero duration")

    @property
    def crosses_midnight(self) -> bool:
        return self.night_end < self.night_start


@dataclass(frozen=True, slots=True)
class CommodityFuturesClock:
    template: FuturesSessionTemplate
    night_trade_dates: dict[date, date]
    trading_dates: frozenset[date]

    def __post_init__(self) -> None:
        if any(
            exchange_date not in self.trading_dates
            for exchange_date in self.night_trade_dates.values()
        ):
            raise ValueError("night session must map to a declared trading date")
        if any(
            exchange_date <= calendar_date
            for calendar_date, exchange_date in self.night_trade_dates.items()
        ):
            raise ValueError("night session must map to a later exchange trade date")

    def trade_date(self, timestamp: datetime) -> date:
        local = AsiaShanghaiClock.localize(timestamp)
        calendar_date = local.date()
        local_time = local.timetz().replace(tzinfo=None)

        if local_time >= self.template.night_start:
            return self._night_trade_date(calendar_date)
        if self.template.crosses_midnight and local_time < self.template.night_end:
            return self._night_trade_date(calendar_date - timedelta(days=1))
        if calendar_date not in self.trading_dates:
            raise ValueError("timestamp is not on a declared trading date")
        return calendar_date

    def settlement_time(self, trade_date: date) -> datetime:
        if trade_date not in self.trading_dates:
            raise ValueError("settlement requires a declared trading date")
        return datetime.combine(
            trade_date,
            self.template.settlement_at,
            tzinfo=SHANGHAI,
        )

    def _night_trade_date(self, calendar_date: date) -> date:
        try:
            return self.night_trade_dates[calendar_date]
        except KeyError as exc:
            raise ValueError("no declared night session for calendar date") from exc

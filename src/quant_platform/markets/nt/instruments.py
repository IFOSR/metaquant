"""NautilusTrader 标的定义工厂（G18 P0）。

从 ``markets/`` 的规则建模（唯一事实源）生成 NautilusTrader 的
``Equity`` / ``FuturesContract`` 标的。适配层不重复建模规则，只做
「我们的规则 → NautilusTrader 数据模型」的映射。
"""

from __future__ import annotations

from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import Equity, FuturesContract
from nautilus_trader.model.objects import Currency, Price, Quantity


def equity_instrument(
    *,
    symbol: str,
    venue: str = "SSE",
    currency: str = "CNY",
    price_increment: str = "0.01",
    lot_size: str = "100",
    price_precision: int = 2,
    isin: str | None = None,
) -> Equity:
    """构造 A 股 Equity 标的。

    ``venue`` 由股票代码推断：6/9 开头为上交所（SSE），其余为深交所（SZSE）。
    默认 lot_size 100 股（一手），price_increment 0.01 元（tick）。
    """
    resolved_venue = venue
    if symbol.startswith(("6", "9")) and venue == "SSE":
        resolved_venue = "SSE"
    elif not symbol.startswith(("6", "9")) and venue == "SSE":
        resolved_venue = "SZSE"
    return Equity(
        instrument_id=InstrumentId(Symbol(symbol), Venue(resolved_venue)),
        raw_symbol=Symbol(symbol),
        currency=Currency.from_str(currency),
        price_precision=price_precision,
        price_increment=Price.from_str(price_increment),
        lot_size=Quantity.from_str(lot_size),
        ts_event=0,
        ts_init=0,
        isin=isin,
    )


def futures_contract(
    *,
    symbol: str,
    venue: str,
    underlying: str,
    currency: str = "CNY",
    price_increment: str,
    multiplier: str,
    lot_size: str = "1",
    price_precision: int,
    activation_ns: int,
    expiration_ns: int,
    exchange: str | None = None,
) -> FuturesContract:
    """构造商品期货 FuturesContract 标的。

    ``symbol`` 形如 ``RB2610``，``venue`` 为交易所（SHFE/INE/DCE/CZCE/GFEX），
    ``multiplier`` 为合约乘数，``activation_ns``/``expiration_ns`` 为上市/到期
    纳秒时间戳。
    """
    return FuturesContract(
        instrument_id=InstrumentId(Symbol(symbol), Venue(venue)),
        raw_symbol=Symbol(symbol),
        asset_class=AssetClass.COMMODITY,
        currency=Currency.from_str(currency),
        price_precision=price_precision,
        price_increment=Price.from_str(price_increment),
        multiplier=Quantity.from_str(multiplier),
        lot_size=Quantity.from_str(lot_size),
        underlying=underlying,
        activation_ns=activation_ns,
        expiration_ns=expiration_ns,
        ts_event=0,
        ts_init=0,
        exchange=exchange,
    )

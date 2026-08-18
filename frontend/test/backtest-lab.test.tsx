import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BacktestLab } from "../components/backtest-lab";
import { quantApiClient } from "../lib/client";
import type { AlphaPoolFactor, BacktestResult } from "../lib/types";
import { renderWithI18n } from "./render";

const factors: AlphaPoolFactor[] = [
  {
    factorIrHash: "a".repeat(64),
    factorId: "classic.cn_futures.momentum_1d",
    instruments: ["AU2612.SHF", "RB2610.SHF"],
    dataStart: "2026-08-01",
    dataEnd: "2026-08-10",
    direction: "LONG_SHORT",
    market: "CN_COMMODITY_FUTURES",
    universe: "futures-liquid",
    horizon: 5,
    policyId: "policy://cn-futures-promotion/v1",
    riskPremium: false,
    lifecycleState: "PROMOTED",
    oosIc: 0.05,
  },
];


const mockBacktestResult = {
  factorIrHash: "a".repeat(64),
  instrumentIds: ["AU2612.SHF", "RB2610.SHF"],
  start: "2026-08-01",
  end: "2026-08-10",
  frequency: "1d",
  dataSource: "snapshot",
  artifactClass: "FORMAL",
  initialCash: 100_000_000,
  lotSize: 1,
  grossOfFees: true,
  metrics: { totalReturn: 0.0113, sharpe: 1.82, maxDrawdown: 0.0042, tradeCount: 6 },
  equityCurve: [
    { date: "2026-08-03", equity: 100_000_000 },
    { date: "2026-08-04", equity: 100_058_000 },
  ],
  trades: [
    { time: "2026-08-04T15:00:00+00:00", instrumentId: "RB2610.SHFE", side: "BUY", quantity: 1, price: 3035.0 },
    { time: "2026-08-06T15:00:00+00:00", instrumentId: "RB2610.SHFE", side: "SELL", quantity: 1, price: 3055.0 },
  ],
  positions: [
    { instrumentId: "RB2610.SHFE", entry: "BUY", peakQty: 1, avgPxOpen: 3035.0, avgPxClose: 3055.0, realizedPnl: 200.0, openedAt: "2026-08-04T15:00:00+00:00", closedAt: "2026-08-06T15:00:00+00:00" },
  ],
  backtestHash: "c".repeat(64),
} satisfies BacktestResult;

const mockCoverage = [
  { instrumentId: "AU2612.SHF", fieldPrefix: "market.eod", sourceId: "ifind-cn", licenseTag: "formal", artifactClass: "FORMAL", rowCount: 250, firstEvent: "2025-08-01T15:00:00+08:00", lastEvent: "2026-08-14T15:00:00+08:00" },
  { instrumentId: "RB2610.SHF", fieldPrefix: "market.eod", sourceId: "ifind-cn", licenseTag: "formal", artifactClass: "FORMAL", rowCount: 250, firstEvent: "2025-08-01T15:00:00+08:00", lastEvent: "2026-08-14T15:00:00+08:00" },
];

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("BacktestLab", () => {
  it("renders factors, params and runs a backtest with details", async () => {
    vi.spyOn(quantApiClient, "runBacktest").mockResolvedValue(mockBacktestResult);
    renderWithI18n(<BacktestLab factors={factors} />);

    expect(screen.getByText("因子回测")).toBeInTheDocument();
    expect(
      screen.getByText("classic.cn_futures.momentum_1d"),
    ).toBeInTheDocument();
    expect(screen.getByText("AU2612.SHF")).toBeInTheDocument();
    // 参数区：周期/手数/初始资金
    expect(screen.getByText("开始日期")).toBeInTheDocument();
    expect(screen.getByText("结束日期")).toBeInTheDocument();
    expect(screen.getByText("每次下单手数")).toBeInTheDocument();
    expect(screen.getByText(/可用数据区间：2026-08-01/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("运行回测"));

    expect(await screen.findByText("回测结果")).toBeInTheDocument();
    expect(screen.getByText("1.13%")).toBeInTheDocument();
    expect(screen.getByText("1.82")).toBeInTheDocument();
    // 持仓回合表：逐回合已实现盈亏
    expect(screen.getByText("持仓回合")).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
    // 逐笔成交表
    expect(screen.getByText("逐笔成交")).toBeInTheDocument();
    expect(screen.getAllByText("RB2610.SHFE").length).toBeGreaterThan(0);
  });

  it("passes the selected instruments, window and sizing to the API", async () => {
    const spy = vi
      .spyOn(quantApiClient, "runBacktest")
      .mockResolvedValue(mockBacktestResult);
    renderWithI18n(<BacktestLab factors={factors} />);

    fireEvent.click(screen.getByLabelText(/RB2610\.SHF/));
    fireEvent.change(screen.getByLabelText("开始日期"), {
      target: { value: "2026-08-03" },
    });
    fireEvent.change(screen.getByLabelText("每次下单手数"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByText("运行回测"));

    await screen.findByText("回测结果");
    expect(spy).toHaveBeenCalledWith({
      factorIrHash: "a".repeat(64),
      instrumentIds: ["AU2612.SHF"],
      startDate: "2026-08-03",
      endDate: "2026-08-10",
      frequency: "1d",
      dataSource: "snapshot",
      lotSize: 2,
      initialCash: 100_000_000,
    });
  });

  it("fetches coverage and shows the badge for realtime source", async () => {
    vi.spyOn(quantApiClient, "getMarketDataCoverage").mockResolvedValue(
      mockCoverage,
    );
    renderWithI18n(<BacktestLab factors={factors} />);

    fireEvent.change(screen.getByLabelText("数据源"), {
      target: { value: "realtime" },
    });

    expect(
      await screen.findByText(/可用数据区间：2025-08-01/),
    ).toBeInTheDocument();
    expect(screen.getByText("FORMAL")).toBeInTheDocument();

    const spy = vi
      .spyOn(quantApiClient, "runBacktest")
      .mockResolvedValue(mockBacktestResult);
    fireEvent.click(screen.getByText("运行回测"));
    await screen.findByText("回测结果");
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ dataSource: "realtime", frequency: "1d" }),
    );
  });

  it("shows an error banner when the backtest fails", async () => {
    vi.spyOn(quantApiClient, "runBacktest").mockRejectedValue(
      new Error("boom"),
    );
    renderWithI18n(<BacktestLab factors={factors} />);

    fireEvent.click(screen.getByText("运行回测"));

    expect(await screen.findByText("回测失败")).toBeInTheDocument();
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("renders an empty state without factors", () => {
    renderWithI18n(<BacktestLab factors={[]} />);
    expect(screen.getByText(/暂无已晋升因子/)).toBeInTheDocument();
  });
});

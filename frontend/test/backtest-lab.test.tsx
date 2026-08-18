import { cleanup, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BacktestLab } from "../components/backtest-lab";
import { quantApiClient } from "../lib/client";
import type { AlphaPoolFactor } from "../lib/types";
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

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("BacktestLab", () => {
  it("renders factors, params and runs a backtest with details", async () => {
    renderWithI18n(<BacktestLab factors={factors} />);

    expect(screen.getByText("Factor backtest")).toBeInTheDocument();
    expect(
      screen.getByText("classic.cn_futures.momentum_1d"),
    ).toBeInTheDocument();
    expect(screen.getByText("AU2612.SHF")).toBeInTheDocument();
    // 参数区：周期/手数/初始资金
    expect(screen.getByText("Start date")).toBeInTheDocument();
    expect(screen.getByText("End date")).toBeInTheDocument();
    expect(screen.getByText("Lot size (lots)")).toBeInTheDocument();
    expect(screen.getByText(/Available data: 2026-08-01/)).toBeInTheDocument();

    fireEvent.click(screen.getByText("Run backtest"));

    expect(await screen.findByText("Results")).toBeInTheDocument();
    expect(screen.getByText("1.13%")).toBeInTheDocument();
    expect(screen.getByText("1.82")).toBeInTheDocument();
    // 净值曲线 + 交易标记
    const chart = screen.getByRole("img", { name: "Equity curve" });
    expect(chart.querySelectorAll("polygon").length).toBe(2);
    // 持仓回合表：逐回合已实现盈亏
    expect(screen.getByText("Position rounds")).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
    // 逐笔成交表
    expect(screen.getByText("Fills")).toBeInTheDocument();
    expect(screen.getAllByText("RB2610.SHFE").length).toBeGreaterThan(0);
  });

  it("passes the selected instruments, window and sizing to the API", async () => {
    const spy = vi.spyOn(quantApiClient, "runBacktest");
    renderWithI18n(<BacktestLab factors={factors} />);

    fireEvent.click(screen.getByLabelText(/RB2610\.SHF/));
    fireEvent.change(screen.getByLabelText("Start date"), {
      target: { value: "2026-08-03" },
    });
    fireEvent.change(screen.getByLabelText("Lot size (lots)"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByText("Run backtest"));

    await screen.findByText("Results");
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
    renderWithI18n(<BacktestLab factors={factors} />);

    fireEvent.change(screen.getByLabelText("Data source"), {
      target: { value: "realtime" },
    });

    expect(
      await screen.findByText(/Available data: 2025-08-01/),
    ).toBeInTheDocument();
    expect(screen.getByText("FORMAL")).toBeInTheDocument();

    const spy = vi.spyOn(quantApiClient, "runBacktest");
    fireEvent.click(screen.getByText("Run backtest"));
    await screen.findByText("Results");
    expect(spy).toHaveBeenCalledWith(
      expect.objectContaining({ dataSource: "realtime", frequency: "1d" }),
    );
  });

  it("shows an error banner when the backtest fails", async () => {
    vi.spyOn(quantApiClient, "runBacktest").mockRejectedValue(
      new Error("boom"),
    );
    renderWithI18n(<BacktestLab factors={factors} />);

    fireEvent.click(screen.getByText("Run backtest"));

    expect(await screen.findByText("Backtest failed")).toBeInTheDocument();
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("renders an empty state without factors", () => {
    renderWithI18n(<BacktestLab factors={[]} />);
    expect(screen.getByText(/No promoted factors/)).toBeInTheDocument();
  });
});

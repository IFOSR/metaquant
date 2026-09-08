import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StrategyChat } from "../components/strategy-chat";
import { quantApiClient } from "../lib/client";
import type { StrategyDraft } from "../lib/types";
import { renderWithI18n } from "./render";

const backtests = [
  {
    backtestHash: "bt-20260907-a",
    start: "2026-03-07",
    end: "2026-09-07",
    frequency: "15m",
    metrics: {
      totalReturn: 0.12,
      sharpe: 1.4,
      maxDrawdown: 0.08,
      tradeCount: 18,
    },
    ranAt: "2026-09-07T08:00:00Z",
  },
  {
    backtestHash: "bt-20260831-b",
    start: "2026-02-01",
    end: "2026-08-31",
    frequency: "1d",
    metrics: {
      totalReturn: -0.03,
      sharpe: 0.2,
      maxDrawdown: 0.11,
      tradeCount: 7,
    },
    ranAt: "2026-08-31T08:00:00Z",
  },
];

function draft(overrides: Partial<StrategyDraft> = {}): StrategyDraft {
  return {
    id: "draft-1",
    market: "CN_COMMODITY_FUTURES",
    kind: "strategy",
    stage: "BACKTESTED",
    state: "DRAFT",
    title: "MACD 级别差策略",
    explanation: "策略已准备好",
    question: "",
    code: null,
    ready: true,
    instrumentIds: [],
    frequency: "1d",
    backtestPlan: null,
    codeTestResult: null,
    backtestResults: backtests,
    paperBinding: null,
    contentHash: null,
    resourceVersion: 1,
    createdAt: "2026-09-07T00:00:00Z",
    updatedAt: "2026-09-07T00:00:00Z",
    messages: [],
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("StrategyChat backtest import", () => {
  it("keeps the import entry disabled when the current draft has no history", async () => {
    vi.spyOn(quantApiClient, "createStrategyDraft").mockResolvedValue(
      draft({ backtestResults: [] }),
    );
    renderWithI18n(<StrategyChat />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "建立一个策略" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    const importButton = await screen.findByRole("button", {
      name: "导入回测结果",
    });
    expect(importButton).toBeDisabled();
  });

  it("selects one history entry, sends only its hash, and clears it after success", async () => {
    vi.spyOn(quantApiClient, "createStrategyDraft").mockResolvedValue(
      draft(),
    );
    const post = vi
      .spyOn(quantApiClient, "postStrategyMessage")
      .mockResolvedValue(draft());
    renderWithI18n(<StrategyChat />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "建立一个策略" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    const importButton = await screen.findByRole("button", {
      name: "导入回测结果",
    });

    fireEvent.click(importButton);
    expect(
      screen.getByRole("dialog", { name: "选择一次历史回测" }),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /2026-03-07 ~ 2026-09-07/ }),
    );
    expect(
      screen.getByRole("status", {
        name: "已导入回测 2026-03-07 ~ 2026-09-07",
      }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "导入回测结果" }));
    fireEvent.click(
      screen.getByRole("button", { name: /2026-02-01 ~ 2026-08-31/ }),
    );
    expect(
      screen.queryByRole("status", {
        name: "已导入回测 2026-03-07 ~ 2026-09-07",
      }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("status", {
        name: "已导入回测 2026-02-01 ~ 2026-08-31",
      }),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "请分析并优化" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    await waitFor(() => {
      expect(post).toHaveBeenCalledWith(
        "draft-1",
        "请分析并优化",
        [],
        "bt-20260831-b",
      );
    });
    expect(
      screen.queryByRole("status", {
        name: "已导入回测 2026-02-01 ~ 2026-08-31",
      }),
    ).not.toBeInTheDocument();
  });

  it("keeps the selected backtest and input when sending fails", async () => {
    vi.spyOn(quantApiClient, "createStrategyDraft").mockResolvedValue(
      draft(),
    );
    vi.spyOn(quantApiClient, "postStrategyMessage").mockRejectedValue(
      new Error("Agent unavailable"),
    );
    renderWithI18n(<StrategyChat />);

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "建立一个策略" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "导入回测结果" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /2026-03-07 ~ 2026-09-07/ }),
    );
    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "分析失败时保留" },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));

    expect(await screen.findByText("Agent unavailable")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue("分析失败时保留");
    expect(
      screen.getByRole("status", {
        name: "已导入回测 2026-03-07 ~ 2026-09-07",
      }),
    ).toBeInTheDocument();
  });
});

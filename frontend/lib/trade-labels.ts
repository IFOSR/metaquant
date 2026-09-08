import type { BacktestTrade } from "./types";

export function positionAction(entry: string): string {
  return entry === "BUY" ? "开多" : "开空";
}

export function tradeAction(
  trade: Pick<BacktestTrade, "side" | "action">,
): string {
  return trade.action?.trim() || (trade.side === "BUY" ? "买入" : "卖出");
}

export function actionTone(action: string): "long" | "short" | "neutral" {
  if (action.includes("多")) return "long";
  if (action.includes("空")) return "short";
  return "neutral";
}

import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { KillSwitch } from "../components/kill-switch";
import type { ExecutionState } from "../lib/types";
import { renderWithI18n } from "./render";

function armed(): ExecutionState {
  return {
    stateId: "cn-a",
    killSwitchState: "ARMED",
    trippedBy: null,
    trippedAt: null,
    reason: null,
    shadowPositions: { "600000.SSE": 100 },
    paperPositions: {},
  };
}

describe("KillSwitch", () => {
  it("renders the armed state with a trip action", () => {
    renderWithI18n(<KillSwitch initialState={armed()} onTrip={vi.fn()} onReset={vi.fn()} />);

    expect(screen.getByText("待命")).toBeDefined();
    expect(screen.getByText("触发熔断")).toBeDefined();
  });

  it("trips the switch when a reason is provided", async () => {
    const onTrip = vi.fn().mockResolvedValue({
      ...armed(),
      killSwitchState: "TRIPPED",
      trippedBy: "risk-officer",
      reason: "data anomaly",
    });
    renderWithI18n(<KillSwitch initialState={armed()} onTrip={onTrip} onReset={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText("触发熔断的原因"), {
      target: { value: "data anomaly" },
    });
    fireEvent.click(screen.getByText("触发熔断"));

    expect(await screen.findByText("订单已阻断。")).toBeDefined();
    expect(onTrip).toHaveBeenCalledWith("data anomaly");
  });

  it("resets the switch from a tripped state", async () => {
    const tripped: ExecutionState = {
      ...armed(),
      killSwitchState: "TRIPPED",
      trippedBy: "risk-officer",
      reason: "data anomaly",
    };
    const onReset = vi.fn().mockResolvedValue(armed());
    renderWithI18n(<KillSwitch initialState={tripped} onTrip={vi.fn()} onReset={onReset} />);

    fireEvent.click(screen.getByText("复位熔断开关"));

    expect(await screen.findByTestId("kill-switch-state")).toHaveTextContent(
      "待命",
    );
    expect(onReset).toHaveBeenCalled();
  });
});

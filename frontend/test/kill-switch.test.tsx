import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { KillSwitch } from "../components/kill-switch";
import type { ExecutionState } from "../lib/types";

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
    render(<KillSwitch initialState={armed()} onTrip={vi.fn()} onReset={vi.fn()} />);

    expect(screen.getByText("ARMED")).toBeDefined();
    expect(screen.getByText("Trip kill switch")).toBeDefined();
  });

  it("trips the switch when a reason is provided", async () => {
    const onTrip = vi.fn().mockResolvedValue({
      ...armed(),
      killSwitchState: "TRIPPED",
      trippedBy: "risk-officer",
      reason: "data anomaly",
    });
    render(<KillSwitch initialState={armed()} onTrip={onTrip} onReset={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText("Reason for tripping the kill switch"), {
      target: { value: "data anomaly" },
    });
    fireEvent.click(screen.getByText("Trip kill switch"));

    expect(await screen.findByText("Orders blocked.")).toBeDefined();
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
    render(<KillSwitch initialState={tripped} onTrip={vi.fn()} onReset={onReset} />);

    fireEvent.click(screen.getByText("Reset kill switch"));

    expect(await screen.findByTestId("kill-switch-state")).toHaveTextContent(
      "ARMED",
    );
    expect(onReset).toHaveBeenCalled();
  });
});

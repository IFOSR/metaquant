import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StateBoundary } from "../components/state-boundary";

describe("StateBoundary", () => {
  it("renders a stale read-only warning and suppresses write actions", () => {
    render(
      <StateBoundary
        state="stale"
        title="Snapshot is stale"
        detail="The event stream is disconnected."
        actionLabel="Retry"
        onAction={() => undefined}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Snapshot is stale");
    expect(screen.getByText("Read-only mode")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it.each([
    ["loading", "Loading session"],
    ["empty", "No authorized jobs"],
    ["error", "Snapshot failed"],
    ["permission", "Capability required"],
    ["long-running", "Run still active"],
  ] as const)("renders the %s state with an explicit title", (state, title) => {
    render(<StateBoundary state={state} title={title} detail="State detail" />);

    expect(screen.getByText(title)).toBeInTheDocument();
    expect(screen.getByText(state.replace("-", " "))).toBeInTheDocument();
  });
});

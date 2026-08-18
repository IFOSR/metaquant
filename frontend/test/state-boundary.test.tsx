import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StateBoundary } from "../components/state-boundary";
import { renderWithI18n } from "./render";

describe("StateBoundary", () => {
  it("renders a stale read-only warning and suppresses write actions", () => {
    renderWithI18n(
      <StateBoundary
        state="stale"
        title="Snapshot is stale"
        detail="The event stream is disconnected."
        actionLabel="Retry"
        onAction={() => undefined}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Snapshot is stale");
    expect(screen.getByText("只读模式")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });

  it.each([
    ["loading", "Loading session", "加载中"],
    ["empty", "No authorized jobs", "空"],
    ["error", "Snapshot failed", "错误"],
    ["permission", "Capability required", "无权限"],
    ["long-running", "Run still active", "长时间运行"],
  ] as const)("renders the %s state with an explicit title", (state, title, label) => {
    renderWithI18n(<StateBoundary state={state} title={title} detail="State detail" />);

    expect(screen.getByText(title)).toBeInTheDocument();
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HomeFeed, type HomeResearch } from "../components/home-feed";
import { renderWithI18n } from "./render";

const items: HomeResearch[] = [
  { id: "1", kind: "strategy", title: "棕榈油策略", market: "CN_COMMODITY_FUTURES", stage: "READY", updatedAt: "2026-09-09", href: "/x" },
  { id: "2", kind: "factor", title: "动量因子", market: "CN_A", stage: "BACKTESTED", updatedAt: "2026-09-08", href: "/y" },
];

describe("HomeFeed", () => {
  it("renders rows", () => {
    renderWithI18n(<HomeFeed items={items} />);
    expect(screen.getByText("棕榈油策略")).toBeInTheDocument();
    expect(screen.getByText("动量因子")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "清空策略" })).toBeInTheDocument();
  });
});

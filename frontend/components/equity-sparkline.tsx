"use client";

import {
  ColorType,
  createChart,
  createSeriesMarkers,
  LineSeries,
  type SeriesMarker,
  type UTCTimestamp,
} from "lightweight-charts";
import { useEffect, useRef } from "react";

import { tradeAction } from "../lib/trade-labels";
import type { BacktestTrade } from "../lib/types";

interface EquityPoint {
  date: string;
  equity: number;
}

function toTimestamp(value: string): UTCTimestamp | null {
  const parsed = Date.parse(
    /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00Z` : value,
  );
  if (!Number.isFinite(parsed)) return null;
  return Math.floor(parsed / 1000) as UTCTimestamp;
}

function chartPoints(points: EquityPoint[]) {
  const values = new Map<number, { time: UTCTimestamp; value: number }>();
  for (const point of points) {
    const time = toTimestamp(point.date);
    if (time === null || !Number.isFinite(point.equity)) continue;
    // A finalized backtest may append a second value at the last bar timestamp.
    // Keep the last value so Lightweight Charts receives strictly increasing time.
    values.set(Number(time), { time, value: point.equity });
  }
  return [...values.values()].sort(
    (left, right) => Number(left.time) - Number(right.time),
  );
}

function markerTime(
  tradeTime: string,
  points: Array<{ time: UTCTimestamp; value: number }>,
): UTCTimestamp | null {
  const time = toTimestamp(tradeTime);
  if (time === null || points.length === 0) return null;
  let closest = points[0];
  let distance = Math.abs(Number(time) - Number(closest.time));
  for (const point of points.slice(1)) {
    const nextDistance = Math.abs(Number(time) - Number(point.time));
    if (nextDistance < distance) {
      closest = point;
      distance = nextDistance;
    }
  }
  return closest.time;
}

function markerForTrade(
  trade: BacktestTrade,
  points: Array<{ time: UTCTimestamp; value: number }>,
  index: number,
): SeriesMarker<UTCTimestamp> | null {
  const time = markerTime(trade.time, points);
  if (time === null) return null;
  const action = tradeAction(trade);
  const long = action.includes("多");
  return {
    id: `${trade.time}-${index}`,
    time,
    position: trade.side === "BUY" ? "belowBar" : "aboveBar",
    shape: trade.side === "BUY" ? "arrowUp" : "arrowDown",
    color: long ? "#3f7666" : "#a54f45",
    text: action,
    size: 1,
  };
}

export function EquitySparkline({
  points,
  trades = [],
}: {
  points: EquityPoint[];
  trades?: BacktestTrade[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || points.length < 2) return;

    const styles = getComputedStyle(container);
    const lineColor =
      styles.getPropertyValue("--chart-line").trim() || "#9d4f43";
    const textColor =
      styles.getPropertyValue("--chart-text").trim() || "#536071";
    const gridColor =
      styles.getPropertyValue("--chart-grid").trim() || "#d8dee5";
    const chart = createChart(container, {
      autoSize: true,
      height: 320,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: gridColor },
        horzLines: { color: gridColor },
      },
      rightPriceScale: {
        borderColor: gridColor,
        scaleMargins: { top: 0.12, bottom: 0.12 },
      },
      timeScale: {
        borderColor: gridColor,
        timeVisible: true,
        secondsVisible: false,
        rightBarStaysOnScroll: true,
        fixLeftEdge: false,
        fixRightEdge: false,
      },
      crosshair: {
        vertLine: { color: "#8d98a7", width: 1, style: 3 },
        horzLine: { color: "#8d98a7", width: 1, style: 3 },
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        mouseWheel: true,
        pinch: true,
        axisPressedMouseMove: true,
      },
    });
    const series = chart.addSeries(LineSeries, {
      color: lineColor,
      lineWidth: 2,
      crosshairMarkerVisible: true,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    const normalized = chartPoints(points);
    series.setData(normalized);
    const markers = createSeriesMarkers(series);
    markers.setMarkers(
      trades
        .map((trade, index) => markerForTrade(trade, normalized, index))
        .filter(
          (marker): marker is SeriesMarker<UTCTimestamp> => marker !== null,
        )
        .sort((left, right) => Number(left.time) - Number(right.time)),
    );
    chart.timeScale().fitContent();
    chartRef.current = chart;

    return () => {
      chartRef.current = null;
      chart.remove();
    };
  }, [points, trades]);

  if (points.length < 2) return null;

  return (
    <div className="equity-chart-shell">
      <div className="equity-chart-toolbar">
        <span className="equity-chart-hint">
          滚轮缩放 · 拖拽平移 · 十字光标查看时间
        </span>
        <button
          type="button"
          className="equity-chart-reset"
          onClick={() => chartRef.current?.timeScale().fitContent()}
        >
          重置视图
        </button>
      </div>
      <div
        ref={containerRef}
        className="sc-sparkline"
        role="img"
        aria-label="可缩放净值曲线"
      />
    </div>
  );
}

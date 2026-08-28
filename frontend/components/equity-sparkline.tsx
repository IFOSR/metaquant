"use client";

interface EquityPoint {
  date: string;
  equity: number;
}

interface TradeMarker {
  time: string;
  side: string;
}

export function EquitySparkline({
  points,
  trades = [],
}: {
  points: EquityPoint[];
  trades?: TradeMarker[];
}) {
  if (points.length < 2) return null;
  const width = 640;
  const height = 150;
  const pad = 8;
  const values = points.map((point) => point.equity);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const stepX = (width - pad * 2) / (points.length - 1);
  const indexCoord = (index: number) => {
    const x = pad + index * stepX;
    const y = pad + (1 - (values[index] - min) / range) * (height - pad * 2);
    return { x, y };
  };
  const coords = points.map((_, index) => {
    const { x, y } = indexCoord(index);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const rising = values[values.length - 1] >= values[0];
  const stroke = rising ? "var(--success)" : "var(--danger)";

  const dateIndex = new Map(points.map((point, index) => [point.date, index]));
  const markers = (trades ?? [])
    .filter((trade) => trade.time)
    .reduce<Array<{ x: number; y: number; buy: boolean; day: string }>>(
      (acc, trade) => {
        const day = trade.time.slice(0, 10);
        const index = dateIndex.get(day);
        if (index === undefined) return acc;
        const { x, y } = indexCoord(index);
        acc.push({ x, y, buy: trade.side === "BUY", day });
        return acc;
      },
      [],
    );

  const finalCoord = indexCoord(values.length - 1);

  return (
    <svg
      className="sc-sparkline"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label="equity curve"
      preserveAspectRatio="none"
    >
      <polyline
        points={coords.join(" ")}
        fill="none"
        stroke={stroke}
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle
        cx={finalCoord.x.toFixed(1)}
        cy={finalCoord.y.toFixed(1)}
        r="3.5"
        fill={stroke}
      />
      {markers.map((marker, index) => {
        const tipY = marker.buy ? marker.y - 2 : marker.y + 2;
        const baseY = marker.buy ? marker.y - 9 : marker.y + 9;
        const fill = marker.buy ? "var(--success)" : "var(--danger)";
        const pointsAttr = `${marker.x.toFixed(1)},${tipY.toFixed(1)} ${
          (marker.x - 4).toFixed(1)
        },${baseY.toFixed(1)} ${(marker.x + 4).toFixed(1)},${baseY.toFixed(1)}`;
        return (
          <polygon key={`${marker.day}-${index}`} points={pointsAttr} fill={fill}>
            <title>
              {marker.buy ? "开仓" : "平仓"} · {marker.day}
            </title>
          </polygon>
        );
      })}
    </svg>
  );
}

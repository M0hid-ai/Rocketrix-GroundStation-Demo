import { useEffect, useRef, useState } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import { formatT, store, type SeriesKey } from "../lib/store";
import type { Phase } from "../lib/types";

export interface SeriesDef {
  key: SeriesKey;
  label: string;
  color: string;
  dash?: boolean;
  width?: number;
}

interface Props {
  title: string;
  unit: string;
  series: SeriesDef[];
  windowSec: number; // 0 = whole session
  decimals?: number;
  hint?: string;
}

const PHASE_SHORT: Record<Phase, string> = {
  IDLE: "IDLE",
  ARMED: "ARM",
  BOOST: "BOOST",
  COAST: "COAST",
  DROGUE: "DROGUE",
  MAIN: "MAIN",
  LANDED: "LAND",
};

function lowerBound(arr: (number | null)[], v: number): number {
  let lo = 0;
  let hi = arr.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if ((arr[mid] as number) < v) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** Draws flight-phase transitions as thin vertical rules with a small label. */
export function phaseMarksPlugin(getMarks: () => { t: number; phase: Phase }[]): uPlot.Plugin {
  return {
    hooks: {
      draw: (u) => {
        const ctx = u.ctx;
        const { top, height, left, width } = u.bbox;
        const [xmin, xmax] = [u.scales.x.min ?? 0, u.scales.x.max ?? 0];
        ctx.save();
        ctx.font = `${10 * devicePixelRatio}px ui-monospace, monospace`;
        let labelRight = -Infinity; // skip labels that would collide with the previous one
        for (const m of getMarks()) {
          if (m.phase === "IDLE" || m.t < xmin || m.t > xmax) continue;
          const x = Math.round(u.valToPos(m.t, "x", true));
          if (x < left || x > left + width) continue;
          ctx.strokeStyle = "rgba(255,255,255,0.18)";
          ctx.setLineDash([3 * devicePixelRatio, 4 * devicePixelRatio]);
          ctx.beginPath();
          ctx.moveTo(x, top);
          ctx.lineTo(x, top + height);
          ctx.stroke();
          const text = PHASE_SHORT[m.phase];
          const tx = x + 4 * devicePixelRatio;
          if (tx > labelRight) {
            ctx.fillStyle = "rgba(200,210,225,0.65)";
            ctx.fillText(text, tx, top + 12 * devicePixelRatio);
            labelRight = tx + ctx.measureText(text).width + 6 * devicePixelRatio;
          }
        }
        ctx.restore();
      },
    },
  };
}

/** Crosshair tooltip listing every visible series at the hovered time. */
export function tooltipPlugin(
  defs: { label: string; color: string }[],
  unit: string,
  decimals: number,
  fmtX: (x: number) => string,
): uPlot.Plugin {
  let tip: HTMLDivElement;
  return {
    hooks: {
      init: (u) => {
        tip = document.createElement("div");
        tip.className = "chart-tip";
        tip.style.display = "none";
        u.over.appendChild(tip);
        u.over.addEventListener("mouseleave", () => (tip.style.display = "none"));
      },
      setCursor: (u) => {
        const idx = u.cursor.idx;
        if (idx == null || u.cursor.left == null || u.cursor.left < 0) {
          tip.style.display = "none";
          return;
        }
        const x = u.data[0][idx];
        let html = `<div style="color:var(--muted);margin-bottom:3px">${fmtX(x)}</div>`;
        defs.forEach((d, i) => {
          if (!u.series[i + 1].show) return;
          const v = u.data[i + 1][idx];
          const val = v == null ? "—" : `${(v as number).toFixed(decimals)} ${unit}`;
          html += `<div class="row"><span class="swatch" style="background:${d.color}"></span>${d.label}<b>${val}</b></div>`;
        });
        tip.innerHTML = html;
        tip.style.display = "block";
        const w = u.over.clientWidth;
        const left = u.cursor.left + 14;
        tip.style.left = `${left + tip.offsetWidth > w ? u.cursor.left - tip.offsetWidth - 14 : left}px`;
        tip.style.top = `${Math.max(0, (u.cursor.top ?? 0) - 20)}px`;
      },
    },
  };
}

export function axisStyle(fmt?: (v: number) => string): uPlot.Axis {
  return {
    stroke: "#8793a3",
    grid: { stroke: "rgba(255,255,255,0.06)", width: 1 },
    ticks: { stroke: "rgba(255,255,255,0.08)", width: 1, size: 4 },
    font: "11px ui-monospace, monospace",
    ...(fmt ? { values: (_u: uPlot, vals: number[]) => vals.map(fmt) } : {}),
  };
}

export default function LiveChart({ title, unit, series, windowSec, decimals = 1, hint }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const plot = useRef<uPlot | null>(null);
  const windowRef = useRef(windowSec);
  const [hidden, setHidden] = useState<Record<string, boolean>>({});
  windowRef.current = windowSec;

  useEffect(() => {
    const el = host.current!;
    const fmtX = (x: number) => formatT(x, store.tZero);
    const opts: uPlot.Options = {
      width: el.clientWidth,
      height: el.clientHeight,
      pxAlign: false,
      legend: { show: false },
      cursor: { points: { size: 7 }, drag: { x: false, y: false } },
      scales: { x: { time: false } },
      axes: [
        axisStyle((v) => {
          if (store.tZero === null) return `${v.toFixed(0)}s`;
          const d = v - store.tZero;
          return `${d < 0 ? "−" : "+"}${Math.abs(d).toFixed(0)}`;
        }),
        { ...axisStyle(), size: 52 },
      ],
      series: [
        {},
        ...series.map((s) => ({
          label: s.label,
          stroke: s.color,
          width: s.width ?? 2,
          dash: s.dash ? [6, 5] : undefined,
          spanGaps: true,
          points: { show: false },
        })),
      ],
      plugins: [
        phaseMarksPlugin(() => store.phaseMarks),
        tooltipPlugin(series, unit, decimals, fmtX),
      ],
    };
    const u = new uPlot(opts, [[], ...series.map(() => [])] as uPlot.AlignedData, el);
    plot.current = u;

    const ro = new ResizeObserver(() => u.setSize({ width: el.clientWidth, height: el.clientHeight }));
    ro.observe(el);

    let seen = -1;
    let raf = 0;
    const tick = () => {
      if (store.dataVersion !== seen) {
        seen = store.dataVersion;
        const t = store.cols.t;
        const n = t.length;
        let start = 0;
        if (windowRef.current > 0 && n) {
          start = lowerBound(t, (t[n - 1] as number) - windowRef.current);
        }
        const data = [t.slice(start), ...series.map((s) => store.cols[s.key].slice(start))];
        u.setData(data as uPlot.AlignedData);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      u.destroy();
      plot.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggle = (i: number, key: string) => {
    const off = !hidden[key];
    setHidden({ ...hidden, [key]: off });
    plot.current?.setSeries(i + 1, { show: !off });
  };

  return (
    <div className="panel">
      <div className="panel-title">
        <span>
          {title} {hint && <span className="hint">· {hint}</span>}
        </span>
        {series.length > 1 && (
          <div className="legend">
            {series.map((s, i) => (
              <span
                key={s.key}
                className={`legend-item ${hidden[s.key] ? "off" : ""}`}
                onClick={() => toggle(i, s.key)}
                title="Show / hide series"
              >
                <span
                  className={`swatch ${s.dash ? "dashed" : ""}`}
                  style={{ background: s.color, color: s.color }}
                />
                {s.label}
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="chart-host" ref={host} />
    </div>
  );
}

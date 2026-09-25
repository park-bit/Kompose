"use client";

import { PriceSignal } from "@/types/travel";

interface Props {
  signal: PriceSignal;
}

const SIGNAL_CONFIG = {
  book_now: {
    bg: "bg-amber-500/10 border-amber-500/30",
    badge: "bg-amber-500/20 text-amber-300 border-amber-500/30",
    indicator: "bg-amber-400",
    label: "Book Recommended",
    desc: "Current fares are in the lower quartile for this route and date.",
  },
  wait: {
    bg: "bg-emerald-500/10 border-emerald-500/30",
    badge: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
    indicator: "bg-emerald-400",
    label: "Fares Expected To Drop",
    desc: "Historical signals suggest prices may soften closer to departure.",
  },
  neutral: {
    bg: "bg-slate-500/10 border-slate-500/20",
    badge: "bg-slate-500/20 text-slate-300 border-slate-500/30",
    indicator: "bg-slate-400",
    label: "Stable Pricing",
    desc: "Fares are tracking within normal expected price bands.",
  },
  unknown: {
    bg: "bg-slate-500/10 border-slate-500/20",
    badge: "bg-slate-500/20 text-slate-300 border-slate-500/30",
    indicator: "bg-slate-400",
    label: "No Strong Signal",
    desc: "Insufficient volume to establish a high-confidence projection.",
  },
};

export default function PriceBanner({ signal }: Props) {
  const config = SIGNAL_CONFIG[signal.signal || "unknown"];

  return (
    <div
      id="price-trend-banner"
      className={`rounded-xl border p-4 ${config.bg} text-sm`}
    >
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${config.indicator} animate-pulse`} />
          <span className="text-xs uppercase font-mono tracking-wider text-slate-400">
            Price Intelligence
          </span>
          <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${config.badge}`}>
            {config.label}
          </span>
        </div>
        {signal.confidence && signal.confidence > 0 && (
          <span className="text-xs font-mono text-slate-400">
            {Math.round(signal.confidence * 100)}% confidence
          </span>
        )}
      </div>

      <p className="text-slate-300 text-xs mt-1">
        {signal.note || config.desc}
      </p>

      {signal.disclaimer && (
        <p className="text-slate-500 text-[11px] mt-1.5 italic">
          {signal.disclaimer}
        </p>
      )}
    </div>
  );
}

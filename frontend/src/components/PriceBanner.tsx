"use client";

import { PriceSignal } from "@/types/travel";

interface Props {
  signal: PriceSignal;
}

const SIGNAL_CONFIG = {
  book_now: {
    bg: "bg-amber-500/20 border-amber-500/40",
    icon: "🔥",
    label: "Book Now",
    text: "text-amber-300",
  },
  wait: {
    bg: "bg-emerald-500/20 border-emerald-500/40",
    icon: "⏳",
    label: "Consider Waiting",
    text: "text-emerald-300",
  },
  neutral: {
    bg: "bg-slate-500/20 border-slate-500/40",
    icon: "📊",
    label: "Neutral",
    text: "text-slate-300",
  },
  unknown: {
    bg: "bg-slate-500/20 border-slate-500/40",
    icon: "📊",
    label: "No Signal",
    text: "text-slate-300",
  },
};

export default function PriceBanner({ signal }: Props) {
  const config = SIGNAL_CONFIG[signal.signal || "unknown"];

  return (
    <div
      id="price-trend-banner"
      className={`rounded-xl border px-4 py-3 ${config.bg} text-sm`}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-base">{config.icon}</span>
        <span className={`font-semibold ${config.text}`}>
          Price Trend: {config.label}
        </span>
        {signal.confidence && signal.confidence > 0 && (
          <span className="ml-auto text-xs text-slate-400">
            {Math.round(signal.confidence * 100)}% confidence
          </span>
        )}
      </div>
      {signal.note && <p className="text-slate-300 text-xs">{signal.note}</p>}
      {signal.disclaimer && (
        <p className="text-slate-500 text-xs mt-1 italic">{signal.disclaimer}</p>
      )}
    </div>
  );
}

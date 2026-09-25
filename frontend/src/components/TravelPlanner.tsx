"use client";

import { useState, useRef, useEffect } from "react";
import { sendChatMessage } from "@/lib/api";
import { ChatResponse, TravelSlots } from "@/types/travel";
import RoadmapView from "@/components/RoadmapView";
import PriceBanner from "@/components/PriceBanner";
import MapView from "@/components/MapView";

export default function TravelPlanner() {
  const [messages, setMessages] = useState([
    {
      role: "assistant" as const,
      content:
        "Hi! Tell me where you want to go, your travel dates, budget, and how you prefer to travel (car, train, flight, or mixed). I'll plan the full trip.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [slots] = useState<TravelSlots>({});
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"plan" | "map">("plan");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setLoading(true);

    try {
      const res = await sendChatMessage(text, sessionId, slots);
      setSessionId(res.session_id);
      setResponse(res);
      setMessages((prev) => [...prev, { role: "assistant", content: res.reply }]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Something went wrong.";
      setMessages((prev) => [...prev, { role: "assistant", content: `Unable to plan trip: ${msg}` }]);
    } finally {
      setLoading(false);
    }
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex h-screen bg-gradient-to-br from-slate-950 via-violet-950/30 to-slate-900 text-white overflow-hidden font-sans">
      {/* Left: chat */}
      <div className="flex flex-col w-full max-w-md border-r border-white/10 bg-black/20 backdrop-blur-xl">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-white/10 shrink-0">
          <div className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center text-lg">✈️</div>
          <div>
            <h1 className="text-sm font-bold text-white">Travel Planner</h1>
            <p className="text-xs text-slate-400">AI-powered trip planning</p>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div
                className={`max-w-[85%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
                  m.role === "user"
                    ? "bg-violet-600 text-white rounded-br-sm"
                    : "bg-white/10 text-slate-100 rounded-bl-sm border border-white/10"
                }`}
              >
                <p className="whitespace-pre-wrap">{m.content}</p>
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="px-4 py-2.5 rounded-2xl rounded-bl-sm bg-white/10 border border-white/10">
                <span className="flex gap-1 items-center h-4">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="w-1.5 h-1.5 rounded-full bg-violet-400 animate-bounce"
                      style={{ animationDelay: `${i * 0.15}s` }}
                    />
                  ))}
                </span>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="border-t border-white/10 px-4 py-3 bg-black/10 shrink-0">
          <div className="flex gap-2 items-end">
            <textarea
              id="chat-input"
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Mumbai to Goa, Dec 15, ₹8000 budget, flight preferred"
              className="flex-1 resize-none bg-white/10 border border-white/20 rounded-xl px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500 transition max-h-28"
            />
            <button
              id="send-button"
              onClick={handleSend}
              disabled={loading || !input.trim()}
              className="shrink-0 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white px-4 py-2.5 rounded-xl text-sm font-medium transition-colors"
            >
              Send
            </button>
          </div>
        </div>
      </div>

      {/* Right: results */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Tabs */}
        <div className="flex border-b border-white/10 px-5 pt-4 gap-5 shrink-0">
          {(["plan", "map"] as const).map((tab) => (
            <button
              key={tab}
              id={`tab-${tab}`}
              onClick={() => setActiveTab(tab)}
              className={`pb-3 text-sm font-medium transition-colors border-b-2 ${
                activeTab === tab
                  ? "border-violet-500 text-violet-300"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              {tab === "plan" ? "📋 Itinerary" : "🗺️ Route Map"}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto">
          {!response ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-3">
              <div className="text-5xl opacity-20">🗺️</div>
              <p className="text-sm">Your travel plan will appear here.</p>
            </div>
          ) : activeTab === "plan" ? (
            <div className="p-4 space-y-4">
              {response.price_signal && !response.clarification_needed && (
                <PriceBanner signal={response.price_signal} />
              )}
              {response.roadmap && !response.clarification_needed ? (
                <RoadmapView roadmap={response.roadmap} />
              ) : (
                <p className="text-center text-slate-400 text-sm py-6">
                  Please answer the question in the chat to continue.
                </p>
              )}
            </div>
          ) : (
            <MapView roadmap={response?.roadmap} />
          )}
        </div>
      </div>
    </div>
  );
}

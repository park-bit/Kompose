"use client";

import { useState, useRef, useEffect } from "react";
import { sendChatMessage } from "@/lib/api";
import { ChatMessage, ChatResponse, TravelSlots } from "@/types/travel";
import RoadmapView from "./RoadmapView";
import PriceBanner from "./PriceBanner";

interface Props {
  initialSlots?: TravelSlots;
}

export default function ChatInterface({ initialSlots = {} }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content: "Hi! Tell me where you want to go, your travel dates, budget, and preferred mode of transport (car, train, flight, or mixed). I'll plan your trip.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [slots, setSlots] = useState<TravelSlots>(initialSlots);
  const [lastResponse, setLastResponse] = useState<ChatResponse | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setLoading(true);

    try {
      const response = await sendChatMessage(text, sessionId, slots);
      setSessionId(response.session_id);
      setLastResponse(response);
      setMessages((prev) => [...prev, { role: "assistant", content: response.reply }]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Something went wrong.";
      setMessages((prev) => [...prev, { role: "assistant", content: `Error: ${msg}` }]);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[80%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-violet-600 text-white rounded-br-sm"
                  : "bg-white/10 text-slate-100 rounded-bl-sm border border-white/10"
              }`}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="px-4 py-3 rounded-2xl rounded-bl-sm bg-white/10 border border-white/10">
              <span className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="w-2 h-2 rounded-full bg-violet-400 animate-bounce"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Price banner + roadmap */}
      {lastResponse?.price_signal && !lastResponse.clarification_needed && (
        <div className="px-4 pb-2">
          <PriceBanner signal={lastResponse.price_signal} />
        </div>
      )}

      {/* Input */}
      <div className="border-t border-white/10 px-4 py-4 bg-black/20 backdrop-blur-sm">
        <div className="flex gap-3 items-end">
          <textarea
            ref={inputRef}
            id="chat-input"
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="e.g. Mumbai to Goa on Dec 15, budget ₹8000, flight preferred"
            className="flex-1 resize-none bg-white/10 border border-white/20 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-400 focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500 transition min-h-[44px] max-h-32"
            style={{ fieldSizing: "content" } as React.CSSProperties}
          />
          <button
            id="send-button"
            onClick={handleSend}
            disabled={loading || !input.trim()}
            className="shrink-0 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white px-5 py-3 rounded-xl text-sm font-medium transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

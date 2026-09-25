"use client";

import { useState, useRef, useEffect } from "react";
import { sendChatMessage } from "@/lib/api";
import { ChatMessage, ChatResponse, TravelSlots } from "@/types/travel";
import RoadmapView from "@/components/RoadmapView";
import PriceBanner from "@/components/PriceBanner";
import MapView from "@/components/MapView";
import SettingsModal from "@/components/SettingsModal";
import { PlaneIcon, ListIcon, MapIcon, SendIcon } from "@/components/Icons";


function renderMarkdown(content: string) {
  const paragraphs = content.split("\n\n");
  return paragraphs.map((para, pIdx) => {
    const lines = para.split("\n");
    return (
      <div key={pIdx} className="mb-2 last:mb-0 space-y-1">
        {lines.map((line, lIdx) => {
          const parts = line.split(/(\*\*[^*]+\*\*)/g);
          return (
            <p key={lIdx} className="leading-relaxed">
              {parts.map((part, i) => {
                if (part.startsWith("**") && part.endsWith("**")) {
                  return (
                    <strong key={i} className="font-semibold text-white">
                      {part.slice(2, -2)}
                    </strong>
                  );
                }
                return part;
              })}
            </p>
          );
        })}
      </div>
    );
  });
}

export default function TravelPlanner() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "State your origin, destination, travel dates, budget, and travel mode (car, train, flight, or mixed). I will generate an optimized itinerary and route.",
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [mode, setMode] = useState<string>("mixed");
  const [budget, setBudget] = useState<number | undefined>(undefined);
  const [carType, setCarType] = useState<string>("sedan");
  const [adults, setAdults] = useState<number>(1);
  const [children, setChildren] = useState<number>(0);
  const [response, setResponse] = useState<ChatResponse | null>(null);
  const [activeTab, setActiveTab] = useState<"plan" | "map">("plan");
  const [showSettings, setShowSettings] = useState(false);
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

    const currentSlots: TravelSlots = {
      mode_preference: mode as any,
      budget,
      car_type: carType as any,
      adults,
      children,
    };

    try {
      const res = await sendChatMessage(text, sessionId, currentSlots);
      setSessionId(res.session_id);
      setResponse(res);
      if (res.roadmap?.budget && !budget) {
        setBudget(res.roadmap.budget);
      }
      setMessages((prev) => [...prev, { role: "assistant", content: res.reply }]);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Something went wrong.";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${msg}` },
      ]);
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

  const showCarOption =
    mode === "car" || mode === "mixed" || mode === "bus_car" || mode === "flight_car";

  return (
    <>
    <div className="flex h-screen bg-[#090a0f] text-slate-100 overflow-hidden font-sans antialiased selection:bg-violet-600 selection:text-white">
      {/* Left: Chat Panel */}
      <div className="flex flex-col w-full max-w-md border-r border-white/[0.08] bg-[#0c0e14] shrink-0">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/[0.08] bg-[#0c0e14]/80 backdrop-blur-md shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-violet-600/20 border border-violet-500/30 flex items-center justify-center text-violet-400">
              <PlaneIcon className="w-4 h-4" />
            </div>
            <div>
              <h1 className="text-sm font-semibold tracking-tight text-white">
                Kompose Travel
              </h1>
              <p className="text-[11px] text-slate-400">Multi-Modal Trip Orchestration</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              System Live
            </span>
            <button
              id="open-settings-btn"
              onClick={() => setShowSettings(true)}
              title="API Keys & Settings"
              className="w-7 h-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors"
              aria-label="Open settings"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                <path fillRule="evenodd" d="M7.84 1.804A1 1 0 018.82 1h2.36a1 1 0 01.98.804l.295 1.473c.497.144.971.342 1.416.587l1.25-.834a1 1 0 011.262.125l1.668 1.667a1 1 0 01.125 1.263l-.834 1.25c.245.445.443.919.587 1.416l1.472.294A1 1 0 0120 10v2a1 1 0 01-.804.98l-1.473.295a7.954 7.954 0 01-.587 1.416l.834 1.25a1 1 0 01-.125 1.262l-1.667 1.668a1 1 0 01-1.263.125l-1.25-.834a7.954 7.954 0 01-1.416.587l-.294 1.472A1 1 0 0110 20H8a1 1 0 01-.98-.804l-.295-1.473a7.954 7.954 0 01-1.416-.587l-1.25.834a1 1 0 01-1.262-.125L1.13 16.177a1 1 0 01-.125-1.263l.834-1.25a7.953 7.953 0 01-.587-1.416L.78 11.98A1 1 0 010 11V9a1 1 0 01.804-.98l1.473-.295c.144-.497.342-.971.587-1.416l-.834-1.25a1 1 0 01.125-1.262L3.823 2.13a1 1 0 011.263-.125l1.25.834a7.953 7.953 0 011.416-.587l.294-1.472zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
        </div>

        {/* Message Stream */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
          {messages.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] px-4 py-2.5 rounded-xl text-sm leading-relaxed ${
                  m.role === "user"
                    ? "bg-violet-600 text-white shadow-md shadow-violet-600/10"
                    : "bg-[#141721] text-slate-200 border border-white/[0.08]"
                }`}
              >
                <div className="text-slate-200">
                  {renderMarkdown(m.content)}
                </div>
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="px-4 py-2.5 rounded-xl bg-[#141721] border border-white/[0.08] flex items-center gap-2 text-xs text-slate-400">
                <span>Calculating itineraries and fares</span>
                <span className="flex gap-1 items-center">
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

        {/* Controls Toolbar: Context filters */}
        <div className="px-4 py-2.5 border-t border-white/[0.08] bg-[#090a0f] text-xs flex flex-wrap items-center gap-2">
          {/* Mode */}
          <div className="flex items-center gap-1.5 text-slate-400">
            <span className="font-mono text-[11px] uppercase tracking-wider">Mode</span>
            <select
              id="mode-select"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              className="bg-[#141721] border border-white/[0.08] rounded-md px-2 py-1 text-slate-200 focus:outline-none focus:border-violet-500 font-sans text-xs cursor-pointer"
            >
              <option value="mixed">Mixed (All Modes)</option>
              <option value="train_bus">Mix: Train + Bus</option>
              <option value="bus_car">Mix: Bus + Car</option>
              <option value="flight_train">Mix: Flight + Train</option>
              <option value="flight_car">Mix: Flight + Car</option>
              <option value="bus">Bus Only</option>
              <option value="train">Train (IRCTC)</option>
              <option value="car">Road Trip</option>
              <option value="flight">Flight Only</option>
            </select>
          </div>

          {/* Budget */}
          <div className="flex items-center gap-1.5 text-slate-400">
            <span className="font-mono text-[11px] uppercase tracking-wider">Budget</span>
            <div className="flex items-center bg-[#141721] border border-white/[0.08] rounded-md px-2 py-1 focus-within:border-violet-500">
              <span className="text-slate-500 text-xs font-mono mr-1">₹</span>
              <input
                id="budget-input"
                type="number"
                placeholder="Flexible"
                min={0}
                step={500}
                value={budget ?? ""}
                onChange={(e) =>
                  setBudget(e.target.value !== "" ? Math.max(0, Number(e.target.value)) : undefined)
                }
                className="w-20 bg-transparent text-slate-200 focus:outline-none font-mono text-xs placeholder:text-slate-600"
              />
            </div>
          </div>

          {/* Car type: show only if mode is car, mixed, or mixed car combination */}
          {showCarOption && (
            <div className="flex items-center gap-1.5 text-slate-400">
              <span className="font-mono text-[11px] uppercase tracking-wider">Vehicle</span>
              <select
                id="vehicle-select"
                value={carType}
                onChange={(e) => setCarType(e.target.value)}
                className="bg-[#141721] border border-white/[0.08] rounded-md px-2 py-1 text-slate-200 focus:outline-none focus:border-violet-500 font-sans text-xs cursor-pointer"
              >
                <option value="hatchback">Hatchback (18 km/l)</option>
                <option value="sedan">Sedan (14 km/l)</option>
                <option value="suv">SUV (10.5 km/l)</option>
                <option value="ev">EV (~2.2/km)</option>
              </select>
            </div>
          )}

          {/* Adults */}
          <div className="flex items-center gap-1.5 text-slate-400">
            <span className="font-mono text-[11px] uppercase tracking-wider">Adults</span>
            <select
              value={adults}
              onChange={(e) => setAdults(Number(e.target.value))}
              className="bg-[#141721] border border-white/[0.08] rounded-md px-2 py-1 text-slate-200 focus:outline-none focus:border-violet-500 cursor-pointer"
            >
              {[1, 2, 3, 4, 5, 6].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>

          {/* Children */}
          <div className="flex items-center gap-1.5 text-slate-400">
            <span className="font-mono text-[11px] uppercase tracking-wider">Kids</span>
            <select
              value={children}
              onChange={(e) => setChildren(Number(e.target.value))}
              className="bg-[#141721] border border-white/[0.08] rounded-md px-2 py-1 text-slate-200 focus:outline-none focus:border-violet-500 cursor-pointer"
            >
              {[0, 1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Input Form with guaranteed Click & Enter submission */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="border-t border-white/[0.08] p-3.5 bg-[#0c0e14] shrink-0"
        >
          <div className="flex gap-2 items-center">
            <textarea
              id="chat-input"
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="e.g. Mumbai to Goa, Dec 15, 8000 budget, train preferred"
              className="flex-1 resize-none bg-[#141721] border border-white/[0.08] rounded-lg px-3.5 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-violet-500 focus:ring-1 focus:ring-violet-500 transition max-h-28"
            />
            <button
              type="submit"
              id="send-button"
              disabled={loading || !input.trim()}
              className="shrink-0 bg-violet-600 hover:bg-violet-500 active:bg-violet-700 disabled:opacity-40 disabled:cursor-not-allowed text-white p-2.5 rounded-lg text-sm font-medium transition cursor-pointer flex items-center justify-center shadow-lg shadow-violet-600/20"
              title="Send message"
            >
              <SendIcon className="w-4 h-4" />
            </button>
          </div>
        </form>
      </div>

      {/* Right: Results Panel */}
      <div className="flex-1 flex flex-col overflow-hidden bg-[#090a0f]">
        {/* Navigation Tabs */}
        <div className="flex border-b border-white/[0.08] px-6 pt-3.5 gap-6 shrink-0 bg-[#0c0e14]/50">
          {(["plan", "map"] as const).map((tab) => (
            <button
              key={tab}
              id={`tab-${tab}`}
              onClick={() => setActiveTab(tab)}
              className={`pb-3 text-xs uppercase tracking-wider font-semibold transition-colors border-b-2 flex items-center gap-2 cursor-pointer ${
                activeTab === tab
                  ? "border-violet-500 text-violet-400"
                  : "border-transparent text-slate-500 hover:text-slate-300"
              }`}
            >
              {tab === "plan" ? (
                <>
                  <ListIcon className="w-3.5 h-3.5" />
                  <span>Itinerary</span>
                </>
              ) : (
                <>
                  <MapIcon className="w-3.5 h-3.5" />
                  <span>Route Map</span>
                </>
              )}
            </button>
          ))}
        </div>

        {/* View Content */}
        <div className="flex-1 overflow-y-auto">
          {!response ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-3">
              <div className="w-12 h-12 rounded-2xl bg-white/[0.02] border border-white/[0.05] flex items-center justify-center text-slate-600">
                <MapIcon className="w-6 h-6" />
              </div>
              <p className="text-sm font-medium text-slate-500">
                Trip breakdown will appear here once query is submitted.
              </p>
            </div>
          ) : activeTab === "plan" ? (
            <div className="p-6 max-w-4xl mx-auto space-y-5">
              {response.price_signal && !response.clarification_needed && (
                <PriceBanner signal={response.price_signal} />
              )}
              {response.roadmap && !response.clarification_needed ? (
                <RoadmapView roadmap={response.roadmap} />
              ) : (
                <div className="p-8 text-center text-slate-400 text-sm bg-[#141721] rounded-xl border border-white/[0.08]">
                  Please answer the clarifying question in the chat to proceed.
                </div>
              )}
            </div>
          ) : (
            <MapView roadmap={response?.roadmap} />
          )}
        </div>
      </div>
    </div>
    <SettingsModal open={showSettings} onClose={() => setShowSettings(false)} />
    </>
  );
}


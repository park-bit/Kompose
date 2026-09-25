"use client";

import { Roadmap, Flight, Hotel, BudgetHotel } from "@/types/travel";
import { TrainIcon, BusIcon, CarIcon, StarIcon, ExternalLinkIcon, UsersIcon } from "@/components/Icons";

interface Props {
  roadmap: Roadmap;
}

function fmt(val?: string | number, currency = "INR") {
  if (!val) return "—";
  const n = Number(val);
  if (isNaN(n)) return String(val);
  return `${currency === "INR" ? "₹" : currency} ${n.toLocaleString("en-IN")}`;
}

function WeatherCard({ weather }: { weather: Roadmap["weather"] }) {
  if (!weather?.forecasts?.length) return null;
  const f = weather.forecasts[0];
  return (
    <div className="bg-[#12151f] border border-white/[0.08] rounded-xl p-4">
      <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-400 mb-2">
        Weather Conditions · {weather.city}
      </h3>
      <div className="flex items-center gap-4 text-sm">
        <span className="text-2xl font-bold text-white tracking-tight">{f.temp_c}°C</span>
        <div className="text-slate-400 text-xs">
          <p className="capitalize text-slate-200">{f.description}</p>
          <p>Humidity {f.humidity}% · Wind {f.wind_kph} km/h</p>
        </div>
      </div>
    </div>
  );
}

function CostBreakdown({ roadmap }: { roadmap: Roadmap }) {
  return (
    <div className="bg-[#12151f] border border-white/[0.08] rounded-xl p-5">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-400">
          Estimated Expense Summary
        </h3>
        {roadmap.passengers && (
          <span className="text-xs bg-violet-500/10 text-violet-400 border border-violet-500/20 px-2.5 py-1 rounded-full flex items-center gap-1.5 font-medium">
            <UsersIcon className="w-3.5 h-3.5" />
            <span>
              {roadmap.passengers.adults} adult(s)
              {roadmap.passengers.children > 0 ? `, ${roadmap.passengers.children} kid(s)` : ""}
              {roadmap.passengers.rooms_needed ? ` · ${roadmap.passengers.rooms_needed} room(s)` : ""}
            </span>
          </span>
        )}
      </div>

      {Object.entries(roadmap.daily_cost || {}).map(([date, costs]) => (
        <div key={date} className="mb-3">
          <p className="text-xs font-mono text-slate-500 mb-2">{date}</p>
          <div className="space-y-1.5 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-400">Transport</span>
              <span className="text-slate-200 font-mono">{fmt(costs.transport)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Accommodation</span>
              <span className="text-slate-200 font-mono">{fmt(costs.hotel)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Food (est.)</span>
              <span className="text-slate-200 font-mono">{fmt(costs.food_estimate)}</span>
            </div>
            <div className="flex justify-between border-t border-white/[0.06] pt-2 mt-2">
              <span className="text-slate-300 font-medium">Day subtotal</span>
              <span className="text-violet-300 font-semibold font-mono">{fmt(costs.total)}</span>
            </div>
          </div>
        </div>
      ))}

      <div className="border-t border-white/[0.1] pt-3 mt-3 flex justify-between items-center">
        <span className="text-slate-200 font-semibold text-sm">Total Projected</span>
        <span
          className={`font-bold font-mono text-lg ${
            roadmap.over_budget ? "text-rose-400" : "text-emerald-400"
          }`}
        >
          {fmt(roadmap.total_estimate)}
        </span>
      </div>
      {roadmap.over_budget && roadmap.budget && (
        <p className="text-rose-400 text-xs mt-2 border-t border-rose-500/20 pt-2">
          Exceeds specified budget of {fmt(roadmap.budget)}. Displaying most affordable routes.
        </p>
      )}
    </div>
  );
}

function TravelModesSection({ roadmap }: { roadmap: Roadmap }) {
  const trainLeg = roadmap.legs?.find((l) => l.mode === "train");
  const busLeg = roadmap.legs?.find((l) => l.mode === "bus");
  const carLeg = roadmap.legs?.find((l) => l.mode === "car");

  if (!trainLeg && !busLeg && !carLeg) return null;

  return (
    <div className="space-y-3">
      <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-400">
        Transport Alternatives
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {trainLeg && (
          <div
            className={`rounded-xl p-4 text-sm transition border ${
              trainLeg.recommended
                ? "border-cyan-500/50 ring-1 ring-cyan-500/30 bg-[#131929] shadow-lg shadow-cyan-500/10"
                : "bg-[#12151f] border-white/[0.08] hover:border-emerald-500/40"
            }`}
          >
            <div className="flex justify-between items-start">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="p-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <TrainIcon className="w-4 h-4" />
                  </span>
                  <span className="font-semibold text-white">{trainLeg.name}</span>
                  {trainLeg.recommended && (
                    <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 shadow-sm">
                      {trainLeg.recommendation_tag || "Top Value"}
                    </span>
                  )}
                  {trainLeg.ai_score !== undefined && (
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/[0.05] text-slate-300 border border-white/[0.08]">
                      AI Score: {trainLeg.ai_score}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-1.5">{trainLeg.disclaimer}</p>
              </div>
              <div className="text-right">
                <span className="font-bold text-emerald-400 font-mono">{fmt(trainLeg.cost)}</span>
                <p className="text-[10px] text-slate-500 font-mono uppercase">Group total</p>
              </div>
            </div>
            {trainLeg.source_url && (
              <div className="mt-3 pt-2.5 border-t border-white/[0.06] flex justify-between items-center">
                <span className="text-xs text-slate-500">Official IRCTC booking</span>
                <a
                  href={trainLeg.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-emerald-400 hover:text-emerald-300 font-medium flex items-center gap-1"
                >
                  <span>Book on IRCTC</span>
                  <ExternalLinkIcon className="w-3 h-3" />
                </a>
              </div>
            )}
          </div>
        )}

        {busLeg && (
          <div
            className={`rounded-xl p-4 text-sm transition border ${
              busLeg.recommended
                ? "border-cyan-500/50 ring-1 ring-cyan-500/30 bg-[#131929] shadow-lg shadow-cyan-500/10"
                : "bg-[#12151f] border-white/[0.08] hover:border-amber-500/40"
            }`}
          >
            <div className="flex justify-between items-start">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="p-1 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
                    <BusIcon className="w-4 h-4" />
                  </span>
                  <span className="font-semibold text-white">{busLeg.name}</span>
                  {busLeg.recommended && (
                    <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 shadow-sm">
                      {busLeg.recommendation_tag || "Top Value"}
                    </span>
                  )}
                  {busLeg.ai_score !== undefined && (
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/[0.05] text-slate-300 border border-white/[0.08]">
                      AI Score: {busLeg.ai_score}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-1.5">{busLeg.disclaimer}</p>
              </div>
              <div className="text-right">
                <span className="font-bold text-amber-400 font-mono">{fmt(busLeg.cost)}</span>
                <p className="text-[10px] text-slate-500 font-mono uppercase">Total fare</p>
              </div>
            </div>
            {busLeg.source_url && (
              <div className="mt-3 pt-2.5 border-t border-white/[0.06] flex justify-between items-center">
                <span className="text-xs text-slate-500">Online bus booking</span>
                <a
                  href={busLeg.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-amber-400 hover:text-amber-300 font-medium flex items-center gap-1"
                >
                  <span>Book Bus</span>
                  <ExternalLinkIcon className="w-3 h-3" />
                </a>
              </div>
            )}
          </div>
        )}

        {carLeg && (
          <div
            className={`rounded-xl p-4 text-sm transition border ${
              carLeg.recommended
                ? "border-cyan-500/50 ring-1 ring-cyan-500/30 bg-[#131929] shadow-lg shadow-cyan-500/10"
                : "bg-[#12151f] border-white/[0.08] hover:border-sky-500/40"
            }`}
          >
            <div className="flex justify-between items-start">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="p-1 rounded bg-sky-500/10 text-sky-400 border border-sky-500/20">
                    <CarIcon className="w-4 h-4" />
                  </span>
                  <span className="font-semibold text-white">{carLeg.name}</span>
                  {carLeg.recommended && (
                    <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 shadow-sm">
                      {carLeg.recommendation_tag || "Top Value"}
                    </span>
                  )}
                  {carLeg.ai_score !== undefined && (
                    <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/[0.05] text-slate-300 border border-white/[0.08]">
                      AI Score: {carLeg.ai_score}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-1.5">{carLeg.disclaimer}</p>
              </div>
              <div className="text-right">
                <span className="font-bold text-sky-400 font-mono">{fmt(carLeg.cost)}</span>
                <p className="text-[10px] text-slate-500 font-mono uppercase">Fuel + Tolls</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function FlightCard({ flight }: { flight: Flight }) {
  const seg = flight.segments?.[0];
  return (
    <div className="bg-[#12151f] border border-white/[0.08] rounded-xl p-3.5 text-sm hover:border-violet-500/40 transition">
      <div className="flex justify-between items-start">
        <div>
          <p className="font-semibold text-white">
            {seg?.from} → {seg?.to}
          </p>
          <p className="text-slate-400 text-xs mt-0.5">
            {seg?.carrier} {seg?.flight_number}
          </p>
          <p className="text-slate-500 text-xs mt-0.5">{seg?.departure}</p>
          {(flight.stops ?? 0) > 0 && (
            <span className="inline-block mt-1 text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">
              {flight.stops} stop(s)
            </span>
          )}
        </div>
        <div className="text-right">
          <p className="font-bold text-violet-300 font-mono">{fmt(flight.price_total, flight.currency)}</p>
          <span className="inline-block text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium mt-1">
            Confirmed
          </span>
          <p className="text-[10px] text-slate-500 mt-0.5">via {flight.source}</p>
        </div>
      </div>
    </div>
  );
}

function HotelCard({ hotel }: { hotel: Hotel }) {
  return (
    <div className="bg-[#12151f] border border-white/[0.08] rounded-xl p-3.5 text-sm hover:border-violet-500/40 transition">
      <div className="flex justify-between items-start">
        <div>
          <p className="font-semibold text-white">{hotel.hotel_name}</p>
          <p className="text-slate-400 text-xs mt-0.5">{hotel.city}</p>
          {hotel.stars && (
            <div className="flex items-center gap-0.5 mt-1">
              {Array.from({ length: hotel.stars }).map((_, idx) => (
                <StarIcon key={idx} className="w-3 h-3 text-amber-400" />
              ))}
            </div>
          )}
        </div>
        <div className="text-right">
          <p className="font-bold text-violet-300 font-mono">
            {fmt(hotel.price_per_night, hotel.currency)}
            <span className="text-xs text-slate-500 font-normal"> /night</span>
          </p>
          <span className="inline-block text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium mt-1">
            Bookable
          </span>
          <p className="text-[10px] text-slate-500 mt-0.5">via {hotel.source}</p>
        </div>
      </div>
    </div>
  );
}

function BudgetHotelCard({ hotel }: { hotel: BudgetHotel }) {
  return (
    <div className="bg-[#12151f] border border-white/[0.08] rounded-xl p-3.5 text-sm hover:border-amber-500/40 transition">
      <div className="flex justify-between items-start">
        <div>
          <p className="font-semibold text-white">{hotel.name}</p>
          {hotel.rating && (
            <div className="flex items-center gap-1 mt-1 text-xs text-amber-400">
              <StarIcon className="w-3 h-3" />
              <span>{hotel.rating} / 5</span>
            </div>
          )}
          <p className="text-xs text-slate-400 mt-1">{hotel.disclaimer}</p>
        </div>
        <div className="text-right">
          <p className="font-bold text-amber-300 font-mono">
            {fmt(hotel.price_starting_from, hotel.currency)}
          </p>
          <p className="text-[10px] text-slate-500 mt-0.5">via {hotel.source}</p>
          {hotel.source_url && (
            <a
              href={hotel.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-violet-400 hover:text-violet-300 flex items-center justify-end gap-1 mt-1.5 font-medium"
            >
              <span>Check price</span>
              <ExternalLinkIcon className="w-3 h-3" />
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

export default function RoadmapView({ roadmap }: Props) {
  return (
    <div id="roadmap-view" className="space-y-5 pb-6">
      <div className="flex justify-between items-end border-b border-white/[0.08] pb-4">
        <div>
          <span className="text-[11px] font-mono uppercase tracking-wider text-violet-400">
            Selected Journey
          </span>
          <h2 className="text-xl font-bold text-white tracking-tight mt-0.5">
            {roadmap.origin} → {roadmap.destination}
          </h2>
        </div>
        <div className="text-right">
          <span className="text-xs font-mono text-slate-400 bg-white/[0.04] border border-white/[0.08] px-2.5 py-1 rounded-md">
            {roadmap.travel_date}
          </span>
        </div>
      </div>

      <CostBreakdown roadmap={roadmap} />
      <TravelModesSection roadmap={roadmap} />
      {roadmap.weather && <WeatherCard weather={roadmap.weather} />}

      {/* Flight options */}
      {(roadmap.all_flights?.length ?? 0) > 0 && (
        <div className="space-y-2.5">
          <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-400">
            Available Flights
          </h3>
          <div className="space-y-2">
            {roadmap.all_flights?.map((f, i) => (
              <FlightCard key={i} flight={f} />
            ))}
          </div>
        </div>
      )}

      {/* Hotel options */}
      {(roadmap.all_hotels?.length ?? 0) > 0 && (
        <div className="space-y-2.5">
          <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-400">
            Standard Accommodations
          </h3>
          <div className="space-y-2">
            {roadmap.all_hotels?.map((h, i) => (
              <HotelCard key={i} hotel={h} />
            ))}
          </div>
        </div>
      )}

      {/* Budget stays */}
      {(roadmap.budget_hotels?.length ?? 0) > 0 && (
        <div className="space-y-2.5">
          <div>
            <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-400">
              Budget Accommodations
            </h3>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Aggregated from external listings. Rates subject to live availability.
            </p>
          </div>
          <div className="space-y-2">
            {roadmap.budget_hotels?.map((h, i) => (
              <BudgetHotelCard key={i} hotel={h} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

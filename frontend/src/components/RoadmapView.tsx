"use client";

import { Roadmap, RouteLeg, Flight, Hotel, BudgetHotel } from "@/types/travel";

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
    <div className="bg-white/5 border border-white/10 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-slate-300 mb-2">
        Weather at {weather.city}
      </h3>
      <div className="flex items-center gap-4 text-sm">
        <span className="text-2xl font-bold text-white">{f.temp_c}°C</span>
        <div className="text-slate-400">
          <p className="capitalize">{f.description}</p>
          <p>Humidity {f.humidity}% · Wind {f.wind_kph} km/h</p>
        </div>
      </div>
    </div>
  );
}

function CostBreakdown({ roadmap }: { roadmap: Roadmap }) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-slate-300 mb-3">Cost Breakdown</h3>
      {Object.entries(roadmap.daily_cost || {}).map(([date, costs]) => (
        <div key={date} className="mb-3">
          <p className="text-xs text-slate-400 mb-1">{date}</p>
          <div className="space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-300">Transport</span>
              <span className="text-white">{fmt(costs.transport)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-300">Hotel</span>
              <span className="text-white">{fmt(costs.hotel)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-300">Food (est.)</span>
              <span className="text-white">{fmt(costs.food_estimate)}</span>
            </div>
            <div className="flex justify-between border-t border-white/10 pt-1 mt-1">
              <span className="text-slate-200 font-medium">Day total</span>
              <span className="text-violet-300 font-semibold">{fmt(costs.total)}</span>
            </div>
          </div>
        </div>
      ))}
      <div className="border-t border-white/20 pt-3 flex justify-between">
        <span className="text-slate-200 font-semibold">Estimated total</span>
        <span
          className={`font-bold text-base ${
            roadmap.over_budget ? "text-rose-400" : "text-emerald-400"
          }`}
        >
          {fmt(roadmap.total_estimate)}
        </span>
      </div>
      {roadmap.over_budget && roadmap.budget && (
        <p className="text-rose-400 text-xs mt-1">
          Exceeds your budget of {fmt(roadmap.budget)} — showing cheapest options.
        </p>
      )}
    </div>
  );
}

function FlightCard({ flight }: { flight: Flight }) {
  const seg = flight.segments?.[0];
  return (
    <div className="bg-white/5 border border-white/10 rounded-lg p-3 text-sm">
      <div className="flex justify-between items-start">
        <div>
          <p className="font-medium text-white">
            {seg?.from} → {seg?.to}
          </p>
          <p className="text-slate-400 text-xs">{seg?.carrier} {seg?.flight_number}</p>
          <p className="text-slate-400 text-xs">{seg?.departure}</p>
          {(flight.stops ?? 0) > 0 && (
            <p className="text-amber-400 text-xs">{flight.stops} stop(s)</p>
          )}
        </div>
        <div className="text-right">
          <p className="font-bold text-violet-300">{fmt(flight.price_total, flight.currency)}</p>
          <p className="text-xs text-emerald-400">Bookable</p>
          <p className="text-xs text-slate-500">via {flight.source}</p>
        </div>
      </div>
    </div>
  );
}

function HotelCard({ hotel }: { hotel: Hotel }) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-lg p-3 text-sm">
      <div className="flex justify-between items-start">
        <div>
          <p className="font-medium text-white">{hotel.hotel_name}</p>
          <p className="text-slate-400 text-xs">{hotel.city}</p>
          {hotel.stars && <p className="text-amber-400 text-xs">{"★".repeat(hotel.stars)}</p>}
        </div>
        <div className="text-right">
          <p className="font-bold text-violet-300">{fmt(hotel.price_per_night, hotel.currency)}/night</p>
          <p className="text-xs text-emerald-400">Bookable</p>
          <p className="text-xs text-slate-500">via {hotel.source}</p>
        </div>
      </div>
    </div>
  );
}

function BudgetHotelCard({ hotel }: { hotel: BudgetHotel }) {
  return (
    <div className="bg-amber-900/20 border border-amber-500/20 rounded-lg p-3 text-sm">
      <div className="flex justify-between items-start">
        <div>
          <p className="font-medium text-white">{hotel.name}</p>
          {hotel.rating && <p className="text-amber-400 text-xs">{"★".repeat(Math.round(hotel.rating))}</p>}
          <p className="text-xs text-slate-400 mt-1">{hotel.disclaimer}</p>
        </div>
        <div className="text-right">
          <p className="font-bold text-amber-300">
            Starting from {fmt(hotel.price_starting_from, hotel.currency)}
          </p>
          <p className="text-xs text-slate-400">via {hotel.source}</p>
          {hotel.source_url && (
            <a
              href={hotel.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-violet-400 hover:text-violet-300 underline"
            >
              Check current price ↗
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

export default function RoadmapView({ roadmap }: Props) {
  return (
    <div id="roadmap-view" className="space-y-4 px-4 pb-6">
      <div className="text-center py-3">
        <h2 className="text-lg font-bold text-white">
          {roadmap.origin} → {roadmap.destination}
        </h2>
        <p className="text-slate-400 text-sm">{roadmap.travel_date}</p>
      </div>

      <CostBreakdown roadmap={roadmap} />
      {roadmap.weather && <WeatherCard weather={roadmap.weather} />}

      {/* Flights */}
      {(roadmap.all_flights?.length ?? 0) > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-2">Flight Options</h3>
          <div className="space-y-2">
            {roadmap.all_flights?.map((f, i) => <FlightCard key={i} flight={f} />)}
          </div>
        </div>
      )}

      {/* Hotels */}
      {(roadmap.all_hotels?.length ?? 0) > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-2">Hotel Options</h3>
          <div className="space-y-2">
            {roadmap.all_hotels?.map((h, i) => <HotelCard key={i} hotel={h} />)}
          </div>
        </div>
      )}

      {/* Budget listings */}
      {(roadmap.budget_hotels?.length ?? 0) > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-1">Budget Stays</h3>
          <p className="text-xs text-slate-500 mb-2">
            Prices from third-party sites. Check source for current rates before booking.
          </p>
          <div className="space-y-2">
            {roadmap.budget_hotels?.map((h, i) => <BudgetHotelCard key={i} hotel={h} />)}
          </div>
        </div>
      )}
    </div>
  );
}

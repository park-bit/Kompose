"use client";

import { useEffect, useRef, useState } from "react";
import "leaflet/dist/leaflet.css";
import { Roadmap } from "@/types/travel";

interface Props {
  roadmap?: Roadmap;
}

const CITY_COORDS: Record<string, [number, number]> = {
  mumbai: [19.076, 72.8777],
  delhi: [28.6139, 77.209],
  "new delhi": [28.6139, 77.209],
  bangalore: [12.9716, 77.5946],
  bengaluru: [12.9716, 77.5946],
  goa: [15.2993, 74.124],
  jaipur: [26.9124, 75.7873],
  hyderabad: [17.385, 78.4867],
  chennai: [13.0827, 80.2707],
  kolkata: [22.5726, 88.3639],
  pune: [18.5204, 73.8567],
  ahmedabad: [23.0225, 72.5714],
  agra: [27.1767, 78.0081],
  varanasi: [25.3176, 82.9739],
  udaipur: [24.5854, 73.7125],
  manali: [32.2432, 77.1892],
  shimla: [31.1048, 77.1734],
  kochi: [9.9312, 76.2673],
  chandigarh: [30.7333, 76.7794],
  amritsar: [31.634, 74.8723],
  dubai: [25.2048, 55.2708],
  singapore: [1.3521, 103.8198],
  london: [51.5074, -0.1278],
  paris: [48.8566, 2.3522],
  "new york": [40.7128, -74.006],
};

async function geocode(place: string): Promise<[number, number] | null> {
  const norm = place.trim().toLowerCase();
  for (const [key, coords] of Object.entries(CITY_COORDS)) {
    if (norm.includes(key) || key.includes(norm)) {
      return coords;
    }
  }

  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(
        place
      )}&format=json&limit=1`,
      { headers: { "User-Agent": "KomposeTravelPlanner/1.0" } }
    );
    if (!res.ok) return null;
    const data = await res.json();
    if (data && data[0]) {
      return [parseFloat(data[0].lat), parseFloat(data[0].lon)];
    }
  } catch {
    // fallback
  }
  return null;
}

export default function MapView({ roadmap }: Props) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const routeLayerRef = useRef<any>(null);
  const [routeInfo, setRouteInfo] = useState<{
    distance?: string;
    duration?: string;
  } | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function initMap() {
      if (!mapContainerRef.current) return;
      const L = (await import("leaflet")).default;

      if (!mapInstanceRef.current && mapContainerRef.current) {
        const map = L.map(mapContainerRef.current, {
          zoomControl: true,
          attributionControl: true,
        }).setView([20.5937, 78.9629], 5);

        const GOOGLE_MAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY;
        const googleTileUrl = GOOGLE_MAPS_KEY
          ? `https://maps.googleapis.com/maps/api/staticmap?center={lat},{lon}&zoom={z}&size=256x256&maptype=roadmap&key=${GOOGLE_MAPS_KEY}`
          : null;

        const osmLayer = L.tileLayer(
          "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
          {
            subdomains: ["a", "b", "c"],
            attribution:
              '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            maxZoom: 19,
          }
        );

        // Google Maps raster tiles (requires Maps JavaScript API or Tile API)
        const googleLayer = GOOGLE_MAPS_KEY
          ? L.tileLayer(
              `https://mt{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}&key=${GOOGLE_MAPS_KEY}`,
              {
                subdomains: ["0", "1", "2", "3"],
                attribution: '&copy; <a href="https://maps.google.com">Google Maps</a>',
                maxZoom: 20,
              }
            )
          : null;

        if (googleLayer) {
          googleLayer.on("tileerror", () => {
            // Google tile failed - swap to OSM silently
            map.removeLayer(googleLayer);
            osmLayer.addTo(map);
          });
          googleLayer.addTo(map);
        } else {
          osmLayer.addTo(map);
        }

        mapInstanceRef.current = map;
      }

      const map = mapInstanceRef.current;
      if (!map) return;

      // Clean existing route layers
      if (routeLayerRef.current) {
        map.removeLayer(routeLayerRef.current);
        routeLayerRef.current = null;
      }

      if (!roadmap?.origin || !roadmap?.destination) {
        return;
      }

      const [originCoords, destCoords] = await Promise.all([
        geocode(roadmap.origin),
        geocode(roadmap.destination),
      ]);

      if (!isMounted || !originCoords || !destCoords) return;

      const layerGroup = L.layerGroup();

      const createPinIcon = (color: string, label: string) =>
        L.divIcon({
          className: "custom-map-pin",
          html: `
            <div style="display:flex;flex-direction:column;align-items:center;transform:translate(-50%,-100%);">
              <span style="background:#0f172a;color:#f8fafc;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:600;white-space:nowrap;box-shadow:0 2px 6px rgba(0,0,0,0.4);border:1px solid ${color};margin-bottom:2px;">
                ${label}
              </span>
              <div style="width:14px;height:14px;background:${color};border:2px solid #ffffff;border-radius:50%;box-shadow:0 2px 5px rgba(0,0,0,0.5);"></div>
            </div>
          `,
          iconSize: [0, 0],
        });

      const startMarker = L.marker(originCoords, {
        icon: createPinIcon("#10b981", roadmap.origin),
      }).bindPopup(`<b>Origin:</b> ${roadmap.origin}`);

      const endMarker = L.marker(destCoords, {
        icon: createPinIcon("#8b5cf6", roadmap.destination),
      }).bindPopup(`<b>Destination:</b> ${roadmap.destination}`);

      startMarker.addTo(layerGroup);
      endMarker.addTo(layerGroup);

      // Fetch OSRM route geometry
      try {
        const osrmUrl = `https://router.project-osrm.org/route/v1/driving/${originCoords[1]},${originCoords[0]};${destCoords[1]},${destCoords[0]}?overview=full&geometries=geojson`;
        const res = await fetch(osrmUrl);
        if (res.ok) {
          const data = await res.json();
          if (data.routes && data.routes[0]) {
            const route = data.routes[0];
            const coordinates = route.geometry.coordinates.map(
              ([lon, lat]: [number, number]) => [lat, lon] as [number, number]
            );

            const polyline = L.polyline(coordinates, {
              color: "#7c3aed",
              weight: 5,
              opacity: 0.85,
              lineJoin: "round",
            });
            polyline.addTo(layerGroup);

            const km = Math.round(route.distance / 1000);
            const hrs = Math.floor(route.duration / 3600);
            const mins = Math.round((route.duration % 3600) / 60);
            setRouteInfo({
              distance: `${km} km`,
              duration: hrs > 0 ? `${hrs}h ${mins}m` : `${mins}m`,
            });
          }
        } else {
          // Direct fallback line
          const fallbackLine = L.polyline([originCoords, destCoords], {
            color: "#7c3aed",
            weight: 4,
            dashArray: "6, 8",
          });
          fallbackLine.addTo(layerGroup);
        }
      } catch {
        const fallbackLine = L.polyline([originCoords, destCoords], {
          color: "#7c3aed",
          weight: 4,
          dashArray: "6, 8",
        });
        fallbackLine.addTo(layerGroup);
      }

      layerGroup.addTo(map);
      routeLayerRef.current = layerGroup;

      const bounds = L.latLngBounds([originCoords, destCoords]);
      map.fitBounds(bounds, { padding: [60, 60], maxZoom: 12 });
      setTimeout(() => map.invalidateSize(), 200);
    }

    initMap();

    return () => {
      isMounted = false;
    };
  }, [roadmap?.origin, roadmap?.destination]);

  return (
    <div className="h-full relative w-full bg-slate-950">
      <div ref={mapContainerRef} className="w-full h-full" id="osm-map" />
      {roadmap?.origin && roadmap?.destination && (
        <div className="absolute top-3 left-3 z-[1000] bg-slate-900/90 backdrop-blur-md rounded-lg px-3 py-2 text-xs text-white border border-slate-700/60 shadow-lg flex items-center gap-2">
          <span className="font-semibold text-emerald-400">{roadmap.origin}</span>
          <span className="text-slate-400">→</span>
          <span className="font-semibold text-purple-400">{roadmap.destination}</span>
          {routeInfo && (
            <span className="text-slate-400 pl-2 border-l border-slate-700">
              {routeInfo.distance} • {routeInfo.duration} (driving)
            </span>
          )}
        </div>
      )}
    </div>
  );
}

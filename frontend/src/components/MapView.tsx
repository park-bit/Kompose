"use client";

import { useEffect, useRef } from "react";
import { Roadmap } from "@/types/travel";

interface Props {
  roadmap?: Roadmap;
}

declare global {
  interface Window {
    google: typeof google;
    initMap: () => void;
  }
}

export default function MapView({ roadmap }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<google.maps.Map | null>(null);

  useEffect(() => {
    const key = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY;
    if (!key || !mapRef.current) return;

    function initMap() {
      if (!mapRef.current) return;
      const map = new window.google.maps.Map(mapRef.current, {
        zoom: 5,
        center: { lat: 20.5937, lng: 78.9629 }, // India center
        mapTypeId: "roadmap",
        styles: [
          { elementType: "geometry", stylers: [{ color: "#1d2c4d" }] },
          { elementType: "labels.text.fill", stylers: [{ color: "#8ec3b9" }] },
          { elementType: "labels.text.stroke", stylers: [{ color: "#1a3646" }] },
          { featureType: "road", elementType: "geometry", stylers: [{ color: "#304a7d" }] },
          { featureType: "water", elementType: "geometry", stylers: [{ color: "#0e1626" }] },
        ],
      });
      mapInstance.current = map;

      if (!roadmap?.origin || !roadmap?.destination) return;

      const directionsService = new window.google.maps.DirectionsService();
      const directionsRenderer = new window.google.maps.DirectionsRenderer({
        polylineOptions: { strokeColor: "#7c3aed", strokeWeight: 4 },
      });
      directionsRenderer.setMap(map);

      directionsService.route(
        {
          origin: roadmap.origin,
          destination: roadmap.destination,
          travelMode: window.google.maps.TravelMode.DRIVING,
        },
        (result, status) => {
          if (status === "OK" && result) {
            directionsRenderer.setDirections(result);
          }
        }
      );
    }

    if (window.google?.maps) {
      initMap();
      return;
    }

    window.initMap = initMap;
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${key}&callback=initMap&libraries=places`;
    script.async = true;
    document.head.appendChild(script);

    return () => {
      document.head.removeChild(script);
    };
  }, [roadmap?.origin, roadmap?.destination]);

  if (!process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY) {
    return (
      <div className="flex items-center justify-center h-full text-slate-500 text-sm">
        Set NEXT_PUBLIC_GOOGLE_MAPS_KEY to enable the map.
      </div>
    );
  }

  return (
    <div className="h-full relative">
      <div ref={mapRef} className="w-full h-full" id="google-map" />
      {roadmap?.origin && roadmap?.destination && (
        <div className="absolute top-3 left-3 bg-black/70 backdrop-blur-sm rounded-lg px-3 py-2 text-xs text-white border border-white/10">
          {roadmap.origin} → {roadmap.destination}
        </div>
      )}
    </div>
  );
}

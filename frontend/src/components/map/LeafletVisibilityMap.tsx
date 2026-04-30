import { useEffect, useMemo } from "react";
import L from "leaflet";
import { Circle, MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";

import type { MapPackPlace, SuburbRank } from "../../api/types";

export type CompanyMapPoint = {
  lat: number;
  lng: number;
  label?: string;
  /** From GET /me: address | name_metro | metro_area | google_places | metro_fallback */
  locationSource?: string | null;
};

type Point = {
  suburb: string;
  rank: number | null;
  lat: number;
  lng: number;
  vol: number;
  /** Geographic zone radius in metres (Leaflet `Circle` — scales with zoom). */
  radiusM: number;
};

/** Same assets as leafletDefaultIconFix — explicit so Marker always renders (custom Pane broke defaults). */
const BLUE_PIN_ICON = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

const PACK_PIN_ICON = L.icon({
  iconUrl: "https://cdn.jsdelivr.net/gh/pointhi/leaflet-color-markers@1.0.0/img/marker-icon-red.png",
  shadowUrl: "https://cdn.jsdelivr.net/gh/pointhi/leaflet-color-markers@1.0.0/img/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

function colorForRank(rank: number | null): string {
  if (rank == null) return "#ef4444";
  if (rank <= 3) return "#10b981";
  if (rank <= 10) return "#f59e0b";
  if (rank <= 20) return "#14b8a6";
  return "#ef4444";
}

function opacityForRank(rank: number | null): number {
  if (rank == null) return 0.28;
  if (rank <= 3) return 0.78;
  if (rank <= 10) return 0.62;
  if (rank <= 20) return 0.48;
  return 0.3;
}

/**
 * Metre radius for suburb “coverage” — constant on the ground, so zoom in/out resizes on screen correctly.
 * Uses population when present; otherwise search-volume proxy.
 */
function radiusMetersForSuburb(population: number | null | undefined, volumeProxy: number): number {
  const pop = typeof population === "number" && population > 0 ? population : 0;
  if (pop > 0) {
    if (pop < 4_000) return 1_400;
    if (pop < 12_000) return 2_000;
    if (pop < 35_000) return 2_800;
    if (pop < 90_000) return 3_500;
    return 4_200;
  }
  const v = Math.max(100, volumeProxy || 100);
  return Math.round(Math.min(4_000, Math.max(1_200, 900 + Math.log10(v) * 450)));
}

function FitToPoints({ points }: { points: Point[] }) {
  const map = useMap();
  useEffect(() => {
    if (!points.length) return;
    if (points.length === 1) {
      map.setView([points[0].lat, points[0].lng], 11);
      return;
    }
    const bounds = points.map((p) => [p.lat, p.lng] as [number, number]);
    map.fitBounds(bounds, { padding: [28, 28], maxZoom: 12 });
  }, [map, points]);
  return null;
}

function sourceHelp(src: string | null | undefined): string {
  switch (src) {
    case "address":
      return "Geocoded from your street address.";
    case "name_metro":
      return "Geocoded from business name + metro.";
    case "metro_area":
      return "Geocoded from metro area.";
    case "google_places":
      return "From Google Places (text search).";
    case "metro_fallback":
      return "Metro CBD anchor — add a full street address in Settings for an exact pin.";
    default:
      return "Your business location.";
  }
}

const LEGEND = [
  { c: "bg-emerald-500", t: "Top 3" },
  { c: "bg-amber-400", t: "Pack 4–10" },
  { c: "bg-teal", t: "Pack 11–20" },
  { c: "bg-red-500", t: "Not visible" },
] as const;

export function LeafletVisibilityMap({
  suburbs,
  companyPoint,
  competitorPins,
  radiusKm,
  heightClass = "h-[400px]",
}: {
  suburbs: SuburbRank[];
  companyPoint?: CompanyMapPoint | null;
  competitorPins?: MapPackPlace[] | null;
  radiusKm?: number | null;
  heightClass?: string;
}) {
  const points = useMemo(
    () =>
      suburbs
        .filter((s) => s.lat != null && s.lng != null)
        .map((s) => {
          const vol = Number(s.monthly_volume_proxy ?? 0);
          return {
            suburb: s.suburb,
            rank: s.rank_position,
            lat: Number(s.lat),
            lng: Number(s.lng),
            vol,
            radiusM: radiusMetersForSuburb(s.population, vol),
          };
        }),
    [suburbs],
  );

  const pins: MapPackPlace[] = [];

  const fitPoints = useMemo(() => {
    const base: Point[] = [...points];
    if (companyPoint) {
      base.push({
        suburb: companyPoint.label ?? "Your business",
        rank: null,
        lat: companyPoint.lat,
        lng: companyPoint.lng,
        vol: 1,
        radiusM: 800,
      });
    }
    // Competitor pins are NOT added to fitPoints — some have bad coordinates
    // from DataForSEO that would zoom the map out to the wrong part of Australia.
    return base;
  }, [points, companyPoint]);

  if (!points.length && !companyPoint && !pins.length) {
    return (
      <div className={`${heightClass} rounded-xl bg-rp-light p-4 text-sm text-rp-tlight`}>
        No suburb coordinates available yet.
      </div>
    );
  }

  const initialLat = companyPoint?.lat ?? points[0]?.lat ?? pins[0]?.lat ?? -37.8136;
  const initialLng = companyPoint?.lng ?? points[0]?.lng ?? pins[0]?.lng ?? 144.9631;

  return (
    <div className={`relative ${heightClass} overflow-hidden rounded-xl border border-rp-border`}>
      <MapContainer center={[initialLat, initialLng]} zoom={10} style={{ height: "100%", width: "100%" }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          subdomains="abcd"
        />
        <FitToPoints points={fitPoints} />

        {points.map((p) => (
          <Circle
            key={`${p.suburb}-${p.lat}-${p.lng}`}
            center={[p.lat, p.lng]}
            radius={p.radiusM}
            pathOptions={{
              color: colorForRank(p.rank),
              fillColor: colorForRank(p.rank),
              fillOpacity: opacityForRank(p.rank),
              weight: 1.25,
            }}
          >
            <Popup>
              <div className="text-xs">
                <div className="font-semibold">{p.suburb}</div>
                <div>Rank: {p.rank == null ? "Not visible" : `#${p.rank}`}</div>
                <div>Monthly volume: {p.vol.toLocaleString()}</div>
                <div className="mt-0.5 text-[10px] text-rp-tlight">
                  Zone ≈ {(p.radiusM / 1000).toFixed(1)} km radius (scales with map zoom)
                </div>
              </div>
            </Popup>
          </Circle>
        ))}


        {companyPoint && radiusKm ? (
          <Circle
            center={[companyPoint.lat, companyPoint.lng]}
            radius={radiusKm * 1000}
            pathOptions={{
              color: "#72C219",
              fillColor: "transparent",
              fillOpacity: 0,
              weight: 2,
              dashArray: "6 4",
            }}
          />
        ) : null}

        {companyPoint ? (
          <Marker
            position={[companyPoint.lat, companyPoint.lng]}
            icon={BLUE_PIN_ICON}
            zIndexOffset={5000}
          >
            <Popup>
              <div className="text-xs">
                <div className="font-semibold text-navy">{companyPoint.label ?? "Your business"}</div>
                <div className="font-mono text-[10px] text-rp-tlight">
                  {companyPoint.lat.toFixed(5)}, {companyPoint.lng.toFixed(5)}
                </div>
                <div className="mt-1 text-[10px] leading-snug text-rp-tlight">{sourceHelp(companyPoint.locationSource)}</div>
              </div>
            </Popup>
          </Marker>
        ) : null}
      </MapContainer>

      {/* In-map legend (SERPMapper-style) — does not block dragging */}
      <div className="pointer-events-none absolute bottom-2 left-2 z-[1000] max-w-[200px] rounded-lg border border-rp-border bg-white/95 px-2.5 py-2 shadow-md backdrop-blur-[2px]">
        <div className="mb-1 text-[9px] font-bold uppercase tracking-wide text-rp-tlight">Visibility</div>
        <div className="flex flex-col gap-1">
          {LEGEND.map(({ c, t }) => (
            <div key={t} className="flex items-center gap-1.5 text-[10px] text-navy">
              <span className={`inline-block h-2 w-2 shrink-0 rounded-sm ${c}`} />
              {t}
            </div>
          ))}
        </div>
        <div className="mt-1.5 border-t border-rp-border pt-1.5 text-[9px] leading-tight text-rp-tlight">
          <span className="font-semibold text-navy">○</span> Rings = suburb zone (km radius, grows/shrinks when you zoom)
        </div>
        <div className="mt-1 text-[9px] leading-tight text-rp-tlight">
          Blue marker = your business location
        </div>
      </div>
    </div>
  );
}

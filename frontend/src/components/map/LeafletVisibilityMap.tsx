import { useEffect, useMemo } from "react";
import L from "leaflet";
import { Circle, MapContainer, Marker, TileLayer, Tooltip, useMap } from "react-leaflet";

import type { MapPackPlace, SuburbRank } from "../../api/types";

export type CompanyMapPoint = {
  lat: number;
  lng: number;
  label?: string;
  address?: string | null;
  locationSource?: string | null;
};

type Point = {
  suburb: string;
  rank: number | null;
  lat: number;
  lng: number;
  radiusM: number;
};

/* ── Colour tokens ─────────────────────────────────────────────── */
const RANK_COLORS = {
  top3:    "#22C55E",
  page1:   "#86EFAC",
  page2:   "#FCD34D",
  missing: "#EF4444",
} as const;

function getRankColor(rank: number | null): string {
  if (rank == null) return RANK_COLORS.missing;
  if (rank <= 3)    return RANK_COLORS.top3;
  if (rank <= 10)   return RANK_COLORS.page1;
  if (rank <= 20)   return RANK_COLORS.page2;
  return RANK_COLORS.missing;
}

function rankLabel(rank: number | null): string {
  if (rank == null) return "Not visible";
  if (rank <= 3)    return `#${rank} · Top 3`;
  if (rank <= 10)   return `#${rank} · Page 1`;
  if (rank <= 20)   return `#${rank} · Page 2`;
  return `#${rank} · Not visible`;
}

function radiusMetersForSuburb(pop: number | null | undefined): number {
  const p = typeof pop === "number" && pop > 0 ? pop : 0;
  if (p > 90_000) return 4_200;
  if (p > 35_000) return 3_500;
  if (p > 12_000) return 2_800;
  if (p > 4_000)  return 2_200;
  return 1_600;
}

const BLUE_PIN_ICON = L.icon({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl:       "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl:     "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41], iconAnchor: [12, 41], popupAnchor: [1, -34], shadowSize: [41, 41],
});

function FitToPoints({ points }: { points: Point[] }) {
  const map = useMap();
  useEffect(() => {
    if (!points.length) return;
    if (points.length === 1) { map.setView([points[0].lat, points[0].lng], 12); return; }
    map.fitBounds(
      points.map((p) => [p.lat, p.lng] as [number, number]),
      { padding: [32, 32], maxZoom: 13 },
    );
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return null;
}

const LEGEND_ITEMS = [
  { color: RANK_COLORS.top3,    label: "Top 3 – #1–3" },
  { color: RANK_COLORS.page1,   label: "Page 1 – #4–10" },
  { color: RANK_COLORS.page2,   label: "Page 2 – #11–20" },
  { color: RANK_COLORS.missing, label: "Not visible" },
] as const;

const TOOLTIP_CSS = `
  .leaflet-overlay-pane svg path { mix-blend-mode: multiply; }
  .leaflet-container { font-family: inherit; }
  .serp-tooltip {
    background: white !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 8px !important;
    box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.12) !important;
    padding: 7px 11px !important;
    font-size: 12px !important;
    line-height: 1.5 !important;
  }
  .serp-tooltip::before { display: none !important; }
`;

export function LeafletVisibilityMap({
  suburbs,
  companyPoint,
  competitorPins: _competitorPins,
  radiusKm,
  radiusLabel,
  heightClass = "h-[420px]",
}: {
  suburbs: SuburbRank[];
  companyPoint?: CompanyMapPoint | null;
  competitorPins?: MapPackPlace[] | null;
  radiusKm?: number | null;
  radiusLabel?: string | null;
  heightClass?: string;
}) {
  const points = useMemo(
    () =>
      suburbs
        .filter((s) => s.lat != null && s.lng != null)
        .map((s) => ({
          suburb:  s.suburb,
          rank:    s.rank_position,
          lat:     Number(s.lat),
          lng:     Number(s.lng),
          radiusM: radiusMetersForSuburb(s.population),
        })),
    [suburbs],
  );

  const fitPoints = useMemo(() => {
    const base = [...points];
    if (companyPoint) {
      base.push({ suburb: "biz", rank: null, lat: companyPoint.lat, lng: companyPoint.lng, radiusM: 800 });
    }
    return base;
  }, [points, companyPoint]);

  const radiusPill = useMemo(() => {
    const parts: string[] = [];
    if (radiusLabel) parts.push(`Radius · ${radiusLabel}`);
    else if (radiusKm) parts.push(`Radius · ${radiusKm} km`);
    if (suburbs.length) parts.push(`${suburbs.length} suburbs`);
    return parts.join(" · ").toUpperCase();
  }, [radiusLabel, radiusKm, suburbs.length]);

  const initialLat = companyPoint?.lat ?? points[0]?.lat ?? -37.8136;
  const initialLng = companyPoint?.lng ?? points[0]?.lng ?? 144.9631;

  if (!points.length && !companyPoint) {
    return (
      <div className={`${heightClass} flex items-center justify-center rounded-2xl bg-slate-50 text-sm text-slate-400`}>
        Complete onboarding to see your suburb visibility map.
      </div>
    );
  }

  return (
    <div
      className={`relative overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm ring-1 ring-slate-200/50 ${heightClass}`}
    >
      <style>{TOOLTIP_CSS}</style>

      <MapContainer
        key={`map-${initialLat}-${initialLng}`}
        center={[initialLat, initialLng]}
        zoom={11}
        style={{ height: "100%", width: "100%" }}
        zoomControl={true}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          subdomains="abcd"
          maxZoom={20}
        />
        <FitToPoints points={fitPoints} />

        {/* Suburb heat circles with hover tooltip */}
        {points.map((p) => {
          const col = getRankColor(p.rank);
          return (
            <Circle
              key={`${p.suburb}-${p.lat}-${p.lng}`}
              center={[p.lat, p.lng]}
              radius={p.radiusM}
              pathOptions={{
                fillColor:   col,
                fillOpacity: 0.38,
                color:       col,
                weight:      0.75,
                opacity:     0.85,
              }}
            >
              <Tooltip
                sticky
                className="serp-tooltip"
                offset={[0, 0]}
              >
                <div className="font-bold text-slate-900">{p.suburb}</div>
                <div style={{ color: col, fontWeight: 600 }}>{rankLabel(p.rank)}</div>
              </Tooltip>
            </Circle>
          );
        })}

        {/* Business pin */}
        {companyPoint && (
          <Marker
            position={[companyPoint.lat, companyPoint.lng]}
            icon={BLUE_PIN_ICON}
            zIndexOffset={5000}
          >
            <Tooltip className="serp-tooltip" offset={[0, -30]}>
              <div className="font-bold text-slate-900">{companyPoint.label ?? "Your business"}</div>
              {companyPoint.address && (
                <div className="text-slate-500">{companyPoint.address}</div>
              )}
            </Tooltip>
          </Marker>
        )}
      </MapContainer>

      {/* Top overlays: business card (left) + radius pill (right) */}
      <div className="pointer-events-none absolute left-0 top-0 z-[1100] flex w-full items-start justify-between p-2.5 sm:p-3">
        {companyPoint?.label && (
          <div className="pointer-events-auto max-w-[min(100%,18rem)] rounded-lg border border-slate-200/80 bg-white/95 px-3 py-2 shadow-sm backdrop-blur">
            <p className="text-xs font-extrabold text-slate-900">{companyPoint.label}</p>
            {companyPoint.address && (
              <p className="text-[10px] leading-snug text-slate-500">{companyPoint.address}</p>
            )}
          </div>
        )}

        {radiusPill && (
          <div className="pointer-events-none hidden rounded-full border border-slate-600/30 bg-slate-900/90 px-2.5 py-1.5 text-[9px] font-extrabold uppercase tracking-wider text-white shadow sm:block">
            {radiusPill}
          </div>
        )}
      </div>

      {/* Bottom-left legend */}
      <div className="pointer-events-none absolute bottom-4 left-4 z-[1000] max-w-[180px] space-y-1.5 rounded-xl bg-white/95 p-3 text-xs shadow-lg backdrop-blur-sm ring-1 ring-slate-200/80">
        {LEGEND_ITEMS.map(({ color, label }) => (
          <div key={label} className="flex items-center gap-2 text-[10px] text-slate-700">
            <span
              className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
              style={{ background: color }}
            />
            {label}
          </div>
        ))}
      </div>
    </div>
  );
}

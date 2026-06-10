import { useEffect, useMemo, useState } from "react";
import L from "leaflet";
import {
  GeoJSON,
  MapContainer,
  Marker,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";

import type { MapPackPlace, SuburbRank } from "../../api/types";
import type { ScanProgress } from "../../hooks/useScanPolling";
import { competitorPackRankLabel } from "../../lib/competitorPackLabel";
import { buildSuburbVoronoiCells } from "../../lib/suburbVoronoi";

export type CompanyMapPoint = {
  lat: number;
  lng: number;
  label?: string;
  address?: string | null;
  locationSource?: string | null;
};

type Point = {
  suburbId: string;
  suburb: string;
  rank: number | null;
  lat: number;
  lng: number;
};

const RANK_COLORS = {
  top3: "#22C55E",
  page1: "#86EFAC",
  page2: "#FCD34D",
  missing: "#EF4444",
} as const;

function getRankColor(rank: number | null): string {
  if (rank == null) return RANK_COLORS.missing;
  if (rank <= 3) return RANK_COLORS.top3;
  if (rank <= 10) return RANK_COLORS.page1;
  if (rank <= 20) return RANK_COLORS.page2;
  return RANK_COLORS.missing;
}

function rankLabel(rank: number | null): string {
  if (rank == null) return "Not visible";
  if (rank <= 3) return `#${rank} · Top 3`;
  if (rank <= 10) return `#${rank} · Page 1`;
  if (rank <= 20) return `#${rank} · Page 2`;
  return `#${rank} · Not visible`;
}

function polygonStyle(color: string) {
  return {
    fillColor: color,
    fillOpacity: 0.5,
    color: "#ffffff",
    weight: 2,
    opacity: 1,
  };
}

const BLUE_PIN_ICON = L.icon({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

/** Screen-pixel box size — grows when zoomed in so competitors stay easy to spot. */
function competitorBoxSizeForZoom(zoom: number): number {
  const min = 18;
  const scaled = min + (zoom - 10) * 2.25;
  return Math.min(32, Math.max(min, Math.round(scaled)));
}

/** Violet pins — distinct from green/yellow/red suburb rank zones. */
const COMPETITOR_PIN_COLOR = "#7C3AED";

function createCompetitorBoxIcon(sizePx: number): L.DivIcon {
  const s = Math.max(18, Math.round(sizePx));
  return L.divIcon({
    className: "competitor-box-marker",
    html: `<div class="competitor-box-marker__inner" style="width:${s}px;height:${s}px;background:${COMPETITOR_PIN_COLOR};"></div>`,
    iconSize: [s, s],
    iconAnchor: [s / 2, s / 2],
  });
}

function CompetitorBoxMarkers({ competitors }: { competitors: MapPackPlace[] }) {
  const map = useMap();
  const [zoom, setZoom] = useState(() => map.getZoom());

  useMapEvents({
    zoomend: () => setZoom(map.getZoom()),
    zoom: () => setZoom(map.getZoom()),
  });

  const sizePx = competitorBoxSizeForZoom(zoom);

  const icon = useMemo(() => createCompetitorBoxIcon(sizePx), [sizePx]);

  return (
    <>
      {competitors.map((c, i) => (
        <Marker
          key={`${c.title}-${c.lat}-${c.lng}-${i}-z${sizePx}`}
          position={[c.lat, c.lng]}
          icon={icon}
          zIndexOffset={2000}
        >
          <Tooltip sticky className="serp-tooltip" direction="top" offset={[0, -6]}>
            <div className="font-bold text-slate-900">{c.title}</div>
            {(() => {
              const packLabel = competitorPackRankLabel(c);
              return packLabel ? (
                <div className="text-slate-600">{packLabel}</div>
              ) : null;
            })()}
            {c.suburb_context ? (
              <div className="text-[10px] text-slate-500">Near {c.suburb_context}</div>
            ) : null}
          </Tooltip>
        </Marker>
      ))}
    </>
  );
}

function FitToPoints({ points }: { points: Point[] }) {
  const map = useMap();
  useEffect(() => {
    if (!points.length) return;
    if (points.length === 1) {
      map.setView([points[0].lat, points[0].lng], 12);
      return;
    }
    map.fitBounds(
      points.map((p) => [p.lat, p.lng] as [number, number]),
      { padding: [32, 32], maxZoom: 13 },
    );
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points.length]);
  return null;
}

const LEGEND_ITEMS = [
  { color: RANK_COLORS.top3, label: "Top 3 – #1–3" },
  { color: RANK_COLORS.page1, label: "Page 1 – #4–10" },
  { color: RANK_COLORS.page2, label: "Page 2 – #11–20" },
  { color: RANK_COLORS.missing, label: "Not visible" },
] as const;

const TOOLTIP_CSS = `
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
  .competitor-box-marker {
    background: transparent !important;
    border: none !important;
  }
  .competitor-box-marker__inner {
    display: flex;
    align-items: center;
    justify-content: center;
    border: 3px solid #ffffff;
    border-radius: 5px;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.55);
    box-sizing: border-box;
    pointer-events: auto;
  }
`;

export function LeafletVisibilityMap({
  suburbs,
  companyPoint,
  competitorPins,
  radiusKm,
  radiusLabel,
  heightClass = "h-[420px]",
  scanProgress,
}: {
  suburbs: SuburbRank[];
  companyPoint?: CompanyMapPoint | null;
  competitorPins?: MapPackPlace[] | null;
  radiusKm?: number | null;
  radiusLabel?: string | null;
  heightClass?: string;
  scanProgress?: ScanProgress | null;
}) {
  const points = useMemo(
    () =>
      suburbs
        .filter((s) => s.lat != null && s.lng != null)
        .map((s) => ({
          suburbId: s.suburb_id,
          suburb: s.suburb,
          rank: s.rank_position,
          lat: Number(s.lat),
          lng: Number(s.lng),
          population: s.population,
        })),
    [suburbs],
  );

  const suburbCells = useMemo(
    () =>
      buildSuburbVoronoiCells(points, {
        companyPoint: companyPoint ?? null,
        radiusKm: radiusKm ?? null,
      }),
    [points, companyPoint, radiusKm],
  );

  const fitPoints = useMemo(() => {
    const base: Point[] = [...points];
    if (companyPoint) {
      base.push({
        suburbId: "biz",
        suburb: "biz",
        rank: null,
        lat: companyPoint.lat,
        lng: companyPoint.lng,
      });
    }
    return base;
  }, [points, companyPoint]);

  const competitors = useMemo(
    () => (competitorPins ?? []).slice(0, 80),
    [competitorPins],
  );

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
      <div
        className={`${heightClass} flex items-center justify-center rounded-2xl bg-slate-50 text-sm text-slate-400`}
      >
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
        center={[initialLat, initialLng]}
        zoom={11}
        style={{ height: "100%", width: "100%" }}
        zoomControl
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          subdomains="abcd"
          maxZoom={20}
        />
        <FitToPoints points={fitPoints} />

        {suburbCells.map((cell) => {
          const col = getRankColor(cell.rank);
          return (
            <GeoJSON
              key={`${cell.suburbId}-${cell.rank ?? "nr"}`}
              data={cell.polygon}
              style={() => polygonStyle(col)}
              onEachFeature={(_feature, layer) => {
                layer.bindTooltip(
                  `<div class="font-bold">${cell.suburb}</div><div style="color:${col};font-weight:600">${rankLabel(cell.rank)}</div>`,
                  { sticky: true, className: "serp-tooltip" },
                );
                layer.on("mouseover", function (this: L.Path) {
                  this.setStyle({ weight: 2.5, fillOpacity: 0.62 });
                });
                layer.on("mouseout", function (this: L.Path) {
                  this.setStyle(polygonStyle(col));
                });
              }}
            />
          );
        })}

        {competitors.length > 0 ? <CompetitorBoxMarkers competitors={competitors} /> : null}

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

      {scanProgress && scanProgress.suburbs_total > 0 ? (
        <div className="pointer-events-none absolute bottom-16 left-1/2 z-[1200] -translate-x-1/2 rounded-full border border-[#72C219]/40 bg-white/95 px-4 py-1.5 text-[11px] font-semibold text-navy shadow-lg backdrop-blur">
          Scanning maps pack… {scanProgress.suburbs_checked}/{scanProgress.suburbs_total} suburbs
          {scanProgress.found > 0 ? ` · ${scanProgress.found} ranked` : ""}
        </div>
      ) : null}

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

      <div className="pointer-events-none absolute bottom-4 left-4 z-[1000] max-w-[200px] space-y-1.5 rounded-xl bg-white/95 p-3 text-xs shadow-lg backdrop-blur-sm ring-1 ring-slate-200/80">
        {LEGEND_ITEMS.map(({ color, label }) => (
          <div key={label} className="flex items-center gap-2 text-[10px] text-slate-700">
            <span
              className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
              style={{ background: color }}
            />
            {label}
          </div>
        ))}
        <p className="border-t border-slate-100 pt-1.5 text-[9px] leading-snug text-slate-500">
          Each disc is your scan suburb only (~1 km). Other names on the map (e.g. Burwood) are not in your grid until you add or scan them.
        </p>
        {competitors.length > 0 ? (
          <div className="flex items-center gap-2 text-[10px] text-slate-600">
            <span
              className="inline-block h-3.5 w-3.5 shrink-0 rounded-sm border-2 border-white shadow-sm"
              style={{ background: COMPETITOR_PIN_COLOR }}
            />
            Competitors ({competitors.length})
          </div>
        ) : null}
      </div>
    </div>
  );
}

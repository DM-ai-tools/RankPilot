/**
 * Local suburb map shapes — one small circle per scanned suburb centroid.
 * Does not paint over neighbouring suburbs on the basemap (Burwood, Ashwood, etc.)
 * that are not in your rp_suburb_grid.
 */

import circle from "@turf/circle";

export type SuburbMapPoint = {
  suburbId: string;
  suburb: string;
  rank: number | null;
  lat: number;
  lng: number;
  population?: number | null;
};

export type SuburbMapCell = {
  suburbId: string;
  suburb: string;
  rank: number | null;
  polygon: GeoJSON.Polygon;
};

/** ~1.1 km — matches SERPMapper fallback; stays inside one suburb, not neighbours. */
const BASE_RADIUS_KM = 1.12;

function localRadiusKm(population: number | null | undefined): number {
  const p = typeof population === "number" && population > 0 ? population : 0;
  if (p > 80_000) return 1.45;
  if (p > 35_000) return 1.32;
  if (p > 15_000) return 1.22;
  return BASE_RADIUS_KM;
}

function haversineKm(a: SuburbMapPoint, b: SuburbMapPoint): number {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const x =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((a.lat * Math.PI) / 180) *
      Math.cos((b.lat * Math.PI) / 180) *
      Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(x)));
}

/** Cap radius so we never reach past the nearest other scanned suburb. */
function cappedRadiusKm(suburb: SuburbMapPoint, all: SuburbMapPoint[]): number {
  let nearest = Infinity;
  for (const other of all) {
    if (other.suburbId === suburb.suburbId) continue;
    nearest = Math.min(nearest, haversineKm(suburb, other));
  }
  const base = localRadiusKm(suburb.population);
  if (!Number.isFinite(nearest) || nearest > 10) return base;
  // Stay inside ~42% of gap to neighbour — leaves map visible between suburbs
  const cap = nearest * 0.42;
  return Math.min(base, Math.max(0.75, cap));
}

/** One local disc per suburb — no giant Voronoi cells over other suburbs on the map. */
export function buildSuburbVoronoiCells(
  suburbs: SuburbMapPoint[],
  _options?: {
    companyPoint?: { lat: number; lng: number } | null;
    radiusKm?: number | null;
  },
): SuburbMapCell[] {
  if (suburbs.length === 0) return [];

  return suburbs.map((s) => {
    const r = cappedRadiusKm(s, suburbs);
    const feat = circle([s.lng, s.lat], r, { steps: 40, units: "kilometers" });
    return {
      suburbId: s.suburbId,
      suburb: s.suburb,
      rank: s.rank,
      polygon: feat.geometry as GeoJSON.Polygon,
    };
  });
}

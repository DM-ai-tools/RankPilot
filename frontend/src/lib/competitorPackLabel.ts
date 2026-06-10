import type { MapPackPlace } from "../api/types";

/** Human-readable pack position for map tooltips (suburb-specific vs aggregated). */
export function competitorPackRankLabel(c: MapPackPlace): string | null {
  const best = c.pack_rank_best ?? c.rank;
  const worst = c.pack_rank_worst ?? c.rank;
  const scans = c.suburb_scan_count ?? 1;

  if (best == null) return null;

  if (scans > 1) {
    if (worst != null && worst !== best) {
      return `Maps pack #${best}–#${worst} across ${scans} suburb scans`;
    }
    return `Maps pack #${best} in ${scans} suburb scans`;
  }

  if (c.suburb_context) {
    return `Maps pack #${best} in ${c.suburb_context}`;
  }
  return `Maps pack #${best}`;
}

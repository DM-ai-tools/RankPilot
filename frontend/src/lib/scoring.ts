/**
 * Visibility score from Google Maps local-pack ranks (per suburb) for a keyword.
 * Mirrors backend `app.lib.visibility_scoring`: population-weighted blend of rank bands 1–20.
 */

export const MAX_VISIBLE_RANK = 20;

export function rankWeight(rank: number | null | undefined): number {
  if (rank == null) return 0;
  const r = Math.floor(Number(rank));
  if (r < 1 || r > MAX_VISIBLE_RANK) return 0;
  if (r <= 3) return 1.0;
  if (r <= 10) return 0.6;
  return 0.3;
}

export type SuburbScoreInput = {
  rank_position: number | null;
  population: number | null;
};

/** SUM(rankWeight * volW) / SUM(1 * volW) * 100; volW = pop/maxPop (equal weights if no pop). */
export function visibilityScoreFromSuburbs(suburbs: SuburbScoreInput[]): number {
  if (!suburbs.length) return 0;
  const pops = suburbs.map((s) => Math.max(s.population ?? 0, 0));
  const maxPop = Math.max(...pops, 0);
  let num = 0;
  let den = 0;
  for (let i = 0; i < suburbs.length; i++) {
    const rw = rankWeight(suburbs[i].rank_position);
    const vw = maxPop <= 0 ? 1 : Math.max(pops[i], 1) / maxPop;
    num += rw * vw;
    den += 1.0 * vw;
  }
  if (den <= 0) return 0;
  return Math.min(100, Math.round((100 * num) / den));
}

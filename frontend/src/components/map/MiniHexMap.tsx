/** Stylised suburb grid matching mockup (not geographic Leaflet). */

export type HexTone = "dark" | "green" | "amber" | "teal" | "red";

const toneCls: Record<HexTone, string> = {
  dark: "bg-black/25 text-white/80",
  green: "bg-emerald-500/70 text-white shadow-sm",
  amber: "bg-amber-500/70 text-white shadow-sm",
  teal: "bg-teal-500/70 text-white shadow-sm",
  red: "bg-red-500/55 text-white shadow-sm",
};

export function MiniHexMap({
  rows,
  className = "h-80",
}: {
  rows: { label: string; tone: HexTone }[][];
  className?: string;
}) {
  return (
    <div
      className={`relative flex items-center justify-center overflow-hidden rounded-xl bg-gradient-to-br from-navy via-navy-mid to-teal ${className}`}
    >
      <div
        className="absolute inset-0 grid gap-1.5 p-4"
        style={{
          gridTemplateColumns: `repeat(${rows[0]?.length ?? 7}, 1fr)`,
          gridTemplateRows: `repeat(${rows.length}, 1fr)`,
        }}
      >
        {rows.flatMap((row, ri) =>
          row.map((cell, ci) => (
            <div
              key={`${ri}-${ci}`}
              className={`flex items-center justify-center rounded-lg text-[10px] font-bold text-white drop-shadow-sm ${toneCls[cell.tone]}`}
            >
              {cell.label}
            </div>
          )),
        )}
      </div>
      <div className="absolute bottom-3.5 left-1/2 flex -translate-x-1/2 gap-4 rounded-full bg-black/50 px-3.5 py-1.5 text-[10px] font-semibold text-white">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-emerald-500" />
          Top 3
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-amber-500" />
          Page 1
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-red-500" />
          Not Ranking
        </span>
      </div>
    </div>
  );
}

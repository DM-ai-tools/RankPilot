import { Badge } from "../ui/Badge";

export function keywordSourceLabel(source: string | undefined): string {
  switch (source) {
    case "ahrefs":
      return "Ahrefs";
    case "dataforseo_keywords_data":
      return "DataForSEO";
    case "rank_history_fallback":
      return "Maps scan (cached)";
    case "none":
      return "Not configured";
    default:
      return source ?? "Unknown";
  }
}

export function KeywordDataSourceBadge({ source }: { source?: string }) {
  const label = keywordSourceLabel(source);
  const isAhrefs = source === "ahrefs";
  return (
    <Badge tone={isAhrefs ? "green" : source === "dataforseo_keywords_data" ? "amber" : "blue"}>
      Data: {label}
    </Badge>
  );
}

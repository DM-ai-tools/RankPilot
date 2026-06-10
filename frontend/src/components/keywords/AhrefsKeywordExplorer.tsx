import { useMutation } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";

import { formatApiError } from "../../api/client";
import { lookupKeywords, type KeywordLookupItem } from "../../api/keywords";
import { Button } from "../ui/Button";
import { Card, CardHeader } from "../ui/Card";

function kdTone(kd: number | null): string {
  if (kd == null) return "text-rp-tlight";
  if (kd <= 10) return "text-emerald-600";
  if (kd <= 30) return "text-[#72C219]";
  if (kd <= 50) return "text-amber-600";
  return "text-red-600";
}

function scoreTone(score: number): string {
  if (score >= 500) return "text-emerald-700 font-bold";
  if (score >= 100) return "text-[#4a8a0f] font-semibold";
  if (score > 0) return "text-rp-tmid";
  return "text-rp-tlight";
}

type Props = {
  onInsert?: (
    phrase: string,
    meta?: { volume?: number | null; difficulty?: number | null; opportunity?: number | null },
  ) => void;
  compact?: boolean;
};

export function AhrefsKeywordExplorer({ onInsert, compact }: Props) {
  const [input, setInput] = useState("");
  const [results, setResults] = useState<KeywordLookupItem[]>([]);
  const [country, setCountry] = useState("au");
  const [apiMessage, setApiMessage] = useState<string | null>(null);

  const lookupMut = useMutation({
    mutationFn: () => lookupKeywords(input.trim(), country),
    onSuccess: (data) => {
      if (data.message && (!data.keywords || data.keywords.length === 0)) {
        setApiMessage(data.message);
        setResults([]);
      } else {
        setApiMessage(data.message ?? null);
        setResults(data.keywords ?? []);
      }
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const q = input.trim();
    if (!q) return;
    void lookupMut.mutate();
  }

  return (
    <Card>
      <CardHeader
        title="Ahrefs keyword checker"
        subtitle="Type keywords (comma or new line) — volume, KD, and opportunity score from live Ahrefs data"
      />
      <div className="space-y-3 p-4">
        <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-2">
          <div className="min-w-[200px] flex-1">
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-rp-tlight">
              Keywords
            </label>
            <textarea
              className="min-h-[72px] w-full rounded-lg border border-rp-border bg-white px-3 py-2 text-[12px] text-navy outline-none ring-[#72C219]/30 focus:ring-2"
              placeholder={"digital marketing melbourne\nseo agency south yarra\ngoogle ads box hill"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              rows={compact ? 2 : 3}
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-rp-tlight">
              Country
            </label>
            <select
              className="rounded-lg border border-rp-border bg-white px-2 py-2 text-[12px] text-navy"
              value={country}
              onChange={(e) => setCountry(e.target.value)}
            >
              <option value="au">Australia (au)</option>
              <option value="nz">New Zealand</option>
              <option value="us">United States</option>
              <option value="gb">United Kingdom</option>
            </select>
          </div>
          <Button type="submit" size="sm" disabled={lookupMut.isPending || !input.trim()}>
            <Search className="h-3.5 w-3.5" />
            {lookupMut.isPending ? "Checking…" : "Check keywords"}
          </Button>
        </form>

        {lookupMut.isError ? (
          <p className="text-[12px] text-red-600">{formatApiError(lookupMut.error)}</p>
        ) : null}
        {apiMessage ? (
          <div className="rounded-lg border border-[#FDE68A] bg-[#FFFBEB] px-3 py-2 text-[12px] text-[#92400E]">
            {apiMessage}
          </div>
        ) : null}

        {results.length > 0 ? (
          <div className="overflow-x-auto rounded-lg border border-rp-border">
            <table className="w-full border-collapse text-left text-[11px]">
              <thead className="bg-rp-light">
                <tr className="border-b border-rp-border text-[10px] font-bold uppercase text-rp-tlight">
                  <th className="px-3 py-2">Keyword</th>
                  <th className="px-3 py-2 text-right">Volume</th>
                  <th className="px-3 py-2 text-center">KD</th>
                  <th className="px-3 py-2">Difficulty</th>
                  <th className="px-3 py-2 text-right">Opportunity</th>
                  {onInsert ? <th className="px-3 py-2">Use</th> : null}
                </tr>
              </thead>
              <tbody>
                {results.map((row) => (
                  <tr key={row.keyword} className="border-b border-[#F0F4F9] hover:bg-[#FAFBFD]">
                    <td className="px-3 py-2 font-semibold text-navy">{row.keyword}</td>
                    <td className="px-3 py-2 text-right text-navy">
                      {row.volume > 0 ? row.volume.toLocaleString() : "—"}
                    </td>
                    <td className={`px-3 py-2 text-center font-bold ${kdTone(row.difficulty)}`}>
                      {row.difficulty != null ? row.difficulty : "—"}
                    </td>
                    <td className="px-3 py-2 text-rp-tmid">{row.competition ?? "—"}</td>
                    <td className={`px-3 py-2 text-right ${scoreTone(row.opportunity_score)}`}>
                      {row.opportunity_score > 0 ? row.opportunity_score.toLocaleString() : "—"}
                    </td>
                    {onInsert ? (
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          className="rounded-md bg-[#E6F4EA] px-2 py-0.5 text-[10px] font-bold text-[#137333] hover:bg-[#CEEAD6]"
                          onClick={() =>
                            onInsert(row.keyword, {
                              volume: row.volume,
                              difficulty: row.difficulty,
                              opportunity: row.opportunity_score,
                            })
                          }
                        >
                          + Add
                        </button>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        <p className="text-[10px] text-rp-tlight">
          <strong>Opportunity</strong> = volume × (100 − KD) — higher means more searches relative to difficulty.
          Sort by this to find valuable keywords for GBP descriptions and landing pages.
        </p>
      </div>
    </Card>
  );
}

import { useQuery } from "@tanstack/react-query";
import { FileText, FilePenLine, Link2, Map, MapPin } from "lucide-react";

import { fetchMonthlyReports } from "../api/reports";
import { useAuthStore } from "../stores/authStore";
import type { MonthlyReport } from "../api/types";
import { TopBar } from "../components/layout/TopBar";
import { Card, CardHeader } from "../components/ui/Card";

function ReportCard({ report }: { report: MonthlyReport }) {
  const month = new Date(report.month + "T00:00:00").toLocaleDateString("en-AU", {
    month: "long",
    year: "numeric",
  });
  const scoreDelta =
    report.visibility_score_start != null && report.visibility_score_end != null
      ? report.visibility_score_end - report.visibility_score_start
      : null;

  return (
    <Card>
      <div className="bg-navy px-6 py-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-[18px] font-extrabold text-white">Monthly SEO Report</div>
            <div className="mt-0.5 text-[12px] text-slate-400">{month}</div>
          </div>
          <div className="text-right">
            <div className="text-[10px] text-slate-400">Powered by</div>
            <div className="text-[14px] font-extrabold text-white">
              Rank<span className="text-[#72C219]">Pilot</span>
            </div>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            {
              label: "Visibility Score",
              value: report.visibility_score_end ?? "—",
              delta: scoreDelta != null ? (scoreDelta >= 0 ? `↑ +${scoreDelta}` : `↓ ${scoreDelta}`) : null,
              deltaColor: scoreDelta != null && scoreDelta >= 0 ? "text-emerald-400" : "text-red-400",
            },
            {
              label: "Top-3 Suburbs",
              value: report.top3_end ?? "—",
              delta: report.top3_start != null && report.top3_end != null
                ? `from ${report.top3_start}`
                : null,
              deltaColor: "text-slate-400",
            },
            {
              label: "New Reviews",
              value: report.reviews_new ?? "—",
              delta: null,
              deltaColor: "",
            },
            {
              label: "Pages Published",
              value: report.pages_published ?? "—",
              delta: null,
              deltaColor: "",
            },
          ].map((s) => (
            <div key={s.label} className="rounded-lg bg-white/[0.07] px-3 py-2.5 text-center">
              <div className="text-[9px] font-bold uppercase tracking-wide text-slate-400">{s.label}</div>
              <div className="mt-1 text-[24px] font-black text-amber-400">{s.value}</div>
              {s.delta ? <div className={`text-[10px] font-semibold ${s.deltaColor}`}>{s.delta}</div> : null}
            </div>
          ))}
        </div>
      </div>
      {report.narrative_text ? (
        <div className="px-6 py-4">
          <div className="text-[11px] font-bold uppercase tracking-wide text-rp-tlight">Summary</div>
          <p className="mt-1 text-[13px] leading-relaxed text-rp-tmid">{report.narrative_text}</p>
        </div>
      ) : null}
      {report.pdf_url ? (
        <div className="border-t border-rp-border px-6 py-3">
          <a
            href={report.pdf_url}
            target="_blank"
            rel="noreferrer"
            className="text-[12px] font-semibold text-[#72C219] hover:underline"
          >
            ↓ Download PDF
          </a>
        </div>
      ) : null}
    </Card>
  );
}

export function ReportsPage() {
  const token = useAuthStore((s) => s.accessToken);

  const reports = useQuery({
    queryKey: ["reports", "monthly", token],
    queryFn: fetchMonthlyReports,
    enabled: Boolean(token),
  });

  const items = reports.data?.items ?? [];

  return (
    <>
      <TopBar
        title="Monthly SEO Report"
        subtitle="Auto-generated on the 1st of each month — visibility, content, citations"
      />
      <div className="flex-1 overflow-y-auto bg-rp-light px-7 py-6">
        {reports.isLoading ? (
          <p className="text-sm text-rp-tlight">Loading reports…</p>
        ) : reports.isError ? (
          <p className="text-sm text-red-500">Failed to load reports.</p>
        ) : null}

        {items.length === 0 && !reports.isLoading ? (
          <Card>
            <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
              <div className="rounded-full bg-rp-light p-3 text-[#72C219]">
                <FileText className="h-6 w-6" />
              </div>
              <div className="text-sm font-semibold text-navy">No reports yet</div>
              <p className="max-w-sm text-xs text-rp-tlight">
                Your first monthly report will be auto-generated at the end of your first complete tracking
                month. It will include visibility score trends, content published, citations fixed, and
                recommended actions for the next month.
              </p>
            </div>
          </Card>
        ) : (
          <div className="space-y-6">
            {items.map((r) => (
              <ReportCard key={r.id} report={r} />
            ))}
          </div>
        )}

        {items.length === 0 ? (
          <div className="mt-4">
            <Card>
              <CardHeader title="What's in your monthly report?" />
              <div className="grid gap-4 p-5 sm:grid-cols-2">
                {[
                  { icon: Map, title: "Maps Visibility Trend", desc: "Suburb rank changes vs. previous month, top-3 wins, and near-miss opportunities." },
                  { icon: FilePenLine, title: "Content Published", desc: "Suburb pages and GBP posts created this month, with SEO scores." },
                  { icon: MapPin, title: "GBP Optimisation", desc: "Weekly posts, Q&A responses, and Google Business Profile health score." },
                  { icon: Link2, title: "Citation Health", desc: "NAP consistency across directories — new fixes and outstanding issues." },
                ].map((f) => (
                  <div key={f.title} className="flex gap-3 rounded-lg bg-rp-light p-3">
                    <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-[#72C219]">
                      <f.icon className="h-4 w-4" />
                    </span>
                    <div>
                      <div className="text-[13px] font-semibold text-navy">{f.title}</div>
                      <div className="text-xs text-rp-tlight">{f.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        ) : null}
      </div>
    </>
  );
}

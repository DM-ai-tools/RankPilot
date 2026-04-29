import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  ChevronDown,
  ChevronUp,
  ListChecks,
  MessageSquare,
  Star,
  TrendingUp,
  Trophy,
  UserCircle2,
} from "lucide-react";

import { fetchCompetitorVelocity, fetchReviewsSummary } from "../api/reviews";
import { formatApiError } from "../api/client";
import { TopBar } from "../components/layout/TopBar";
import { Card, CardHeader } from "../components/ui/Card";
import { useAuthStore } from "../stores/authStore";
import type { ReviewItemRow } from "../api/types";

/* ── helpers ──────────────────────────────────────────────────── */
function fmtNum(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return String(n);
}
function fmtRating(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(1);
}

/* ── Star row ─────────────────────────────────────────────────── */
function StarRow({ rating }: { rating: number | null }) {
  if (rating == null) return null;
  const full = Math.round(rating);
  return (
    <span className="inline-flex gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <Star
          key={i}
          className={`h-3 w-3 ${i < full ? "fill-amber-400 text-amber-400" : "text-gray-300"}`}
        />
      ))}
    </span>
  );
}

/* ── AI draft block under each review ────────────────────────── */
function AiDraftBlock({ review }: { review: ReviewItemRow }) {
  const [open, setOpen] = useState(false);

  const isPositive = (review.rating ?? 5) >= 4;
  const draft = isPositive
    ? `Thank you so much for your kind words, ${review.profile_name?.split(" ")[0] ?? "there"}! We're really glad we could help and truly appreciate you taking the time to share your experience. It was a pleasure working with you — don't hesitate to reach out any time! 🙏`
    : `Thank you for your honest feedback, ${review.profile_name?.split(" ")[0] ?? "there"}. We sincerely apologise for falling short of your expectations. Your experience matters to us and we'd love the opportunity to make it right — please contact us directly so we can resolve this for you.`;

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 rounded-md bg-rp-light px-2.5 py-1 text-[11px] font-semibold text-rp-tmid transition hover:bg-[#72C219]/10 hover:text-[#72C219]"
      >
        <Bot className="h-3 w-3" />
        AI Response draft
        {open ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
      </button>

      {open && (
        <div className="mt-2 rounded-lg border border-[#72C219]/25 bg-[#72C219]/6 px-3 py-2.5">
          <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-[#72C219]">
            <Bot className="h-3 w-3" />
            AI Draft — awaiting approval
          </div>
          <p className="text-[12px] leading-relaxed text-rp-tmid">{draft}</p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              className="rounded px-2.5 py-1 text-[11px] font-semibold text-white transition"
              style={{ backgroundColor: "#72C219" }}
            >
              Approve &amp; Publish
            </button>
            <button
              type="button"
              className="rounded border border-rp-border bg-white px-2.5 py-1 text-[11px] font-semibold text-rp-tmid hover:border-[#72C219] transition"
            >
              Edit
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Velocity bar ─────────────────────────────────────────────── */
function VelocityBar({
  label,
  isYou,
  rate,
  maxRate,
  color,
}: {
  label: string;
  isYou?: boolean;
  rate: number;
  maxRate: number;
  color: string;
}) {
  const pct = maxRate > 0 ? Math.round((rate / maxRate) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <div className="w-44 shrink-0 text-[12px] font-semibold text-navy truncate">
        {label}
        {isYou && (
          <span className="ml-1.5 rounded-full bg-[#72C219]/15 px-1.5 py-0.5 text-[10px] font-bold text-[#72C219]">
            you
          </span>
        )}
      </div>
      <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-rp-border">
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <div className="w-14 text-right text-[12px] font-bold" style={{ color }}>
        {rate}/mo
      </div>
    </div>
  );
}

/* ── Competitor bar color by relative performance ──────────────── */
function competitorColor(myRate: number, theirRate: number): string {
  if (theirRate > myRate * 1.2) return "#EF4444";   // faster → red threat
  if (theirRate > myRate * 0.8) return "#F59E0B";   // similar → amber
  return "#6B7280";                                  // slower → grey
}

/* ── Main page ────────────────────────────────────────────────── */
export function ReviewsPage() {
  const token = useAuthStore((s) => s.accessToken);
  const q = useQuery({
    queryKey: ["reviews", "summary", token],
    queryFn: fetchReviewsSummary,
    enabled: Boolean(token),
    staleTime: 60_000,
  });

  const cv = useQuery({
    queryKey: ["reviews", "competitors", token],
    queryFn: fetchCompetitorVelocity,
    enabled: Boolean(token),
    staleTime: 5 * 60_000,
  });

  const d = q.data;
  const total   = d?.reviews_total_google;
  const avg     = d?.average_rating;
  const newMo   = d?.new_this_month ?? 0;
  const batch   = d?.items_returned ?? 0;
  const title   = d?.business_title ?? cv.data?.client_title ?? "Your Business";

  /* Build velocity chart data from real competitors */
  const yourMonthly = newMo > 0 ? newMo : Math.round((total ?? 0) / 12);
  const realCompetitors = (cv.data?.competitors ?? []).map((c) => ({
    label: c.title,
    rate:  c.estimated_monthly ?? 0,
    color: competitorColor(yourMonthly, c.estimated_monthly ?? 0),
    reviews_count: c.reviews_count,
    rating: c.rating,
  }));

  const allRates = [yourMonthly, ...realCompetitors.map((c) => c.rate)];
  const maxRate  = Math.max(...allRates, 1);

  const fastest   = realCompetitors.reduce((a, b) => (a.rate > b.rate ? a : b), { rate: 0, label: "" });
  const hasGap    = fastest.rate > yourMonthly;
  const noScanData = !cv.isLoading && (cv.data?.competitors ?? []).length === 0;

  return (
    <>
      <TopBar
        title="Review Velocity"
        subtitle="Google reviews from your listing (DataForSEO Business Data API)"
      />
      <div className="flex-1 overflow-y-auto bg-rp-light px-7 py-6">

        {/* ── KPI cards ───────────────────────────────────────── */}
        <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[
            {
              label: "Total Reviews",
              icon: Star,
              value: q.isLoading ? "..." : fmtNum(total),
              desc: "on Google",
            },
            {
              label: "Average Rating",
              icon: Trophy,
              value: q.isLoading ? "..." : fmtRating(avg),
              desc: "Out of 5.0",
              star: true,
            },
            {
              label: "New This Month",
              icon: TrendingUp,
              value: q.isLoading ? "..." : String(newMo),
              desc: newMo >= 4 ? "Target: 4+ ✓" : "Target: 4+",
            },
            {
              label: "Reviews Loaded",
              icon: ListChecks,
              value: q.isLoading ? "..." : String(batch),
              desc: "Recent rows from DataForSEO",
            },
          ].map((s) => (
            <div
              key={s.label}
              className="rounded-card border border-rp-border bg-white px-5 py-4 shadow-card"
            >
              <div className="mb-2 inline-flex rounded-lg bg-[#72C219]/15 p-2 text-[#72C219]">
                <s.icon className="h-4 w-4" />
              </div>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-rp-tlight">
                {s.label}
              </div>
              <div className="mt-1 flex items-baseline gap-1.5">
                <span className="text-[28px] font-extrabold leading-none text-navy">{s.value}</span>
                {s.star && avg != null && (
                  <Star className="h-5 w-5 fill-amber-400 text-amber-400" />
                )}
              </div>
              <div className="mt-0.5 text-[10px] text-rp-tlight">{s.desc}</div>
            </div>
          ))}
        </div>

        {/* ── Two-column layout ───────────────────────────────── */}
        <div className="grid gap-5 xl:grid-cols-2">

          {/* ── Review Velocity vs Competitors ──────────────── */}
          <Card>
            <CardHeader title="Review Velocity vs Competitors" />
            <div className="space-y-3 px-5 pb-5">

              {cv.isLoading && (
                <div className="py-6 text-center text-[12px] text-rp-tlight">
                  Loading competitor data...
                </div>
              )}

              {!cv.isLoading && (
                <>
                  {/* Your business row */}
                  <VelocityBar
                    label={title}
                    isYou
                    rate={yourMonthly}
                    maxRate={maxRate}
                    color="#72C219"
                  />

                  {/* Real competitors from scan data */}
                  {realCompetitors.map((c) => (
                    <div key={c.label}>
                      <VelocityBar
                        label={c.label}
                        rate={c.rate}
                        maxRate={maxRate}
                        color={c.color}
                      />
                      {c.reviews_count != null && (
                        <div className="ml-[11.5rem] mt-0.5 text-[10px] text-rp-tlight">
                          {c.reviews_count} total reviews
                          {c.rating != null ? ` · ${c.rating.toFixed(1)}★` : ""}
                        </div>
                      )}
                    </div>
                  ))}

                  {noScanData && (
                    <div className="rounded-lg border border-rp-border bg-rp-light px-3 py-3 text-[12px] text-rp-tmid">
                      {cv.data?.note ?? "Run a Maps scan to populate real competitor data."}
                    </div>
                  )}

                  {hasGap && fastest.label && (
                    <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">
                      <span className="font-bold">⚡ Gap alert:</span>{" "}
                      {fastest.label} gets ~{fastest.rate}/mo. Target {fastest.rate + 2}+ to close the gap.
                    </div>
                  )}

                  {cv.data?.note && !noScanData && (
                    <p className="pt-1 text-[10px] text-rp-tlight">{cv.data.note}</p>
                  )}
                </>
              )}
            </div>
          </Card>

          {/* ── Placeholder for SMS card (coming soon) ──────── */}
          <Card>
            <CardHeader title="SMS Review Requests" />
            <div className="flex flex-col items-center justify-center gap-3 px-6 py-10 text-center">
              <div className="rounded-full bg-rp-light p-3 text-[#72C219]">
                <MessageSquare className="h-6 w-6" />
              </div>
              <div className="text-sm font-semibold text-navy">SMS Integration Coming Soon</div>
              <p className="max-w-xs text-[12px] leading-relaxed text-rp-tlight">
                Automated SMS review requests will appear here once the integration is set up.
                You'll be able to send, track, and manage review requests from this panel.
              </p>
            </div>
          </Card>
        </div>

        {/* ── Recent Reviews + AI Responses ───────────────────── */}
        <div className="mt-5">
          <Card>
            <CardHeader title="Recent Reviews + AI Responses" />

            {q.isLoading && (
              <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center text-sm text-rp-tlight">
                Loading reviews...
              </div>
            )}
            {q.isError && (
              <div className="px-6 py-10 text-center text-sm text-red-700">
                {formatApiError(q.error)}
              </div>
            )}

            {q.isSuccess && (
              <div className="px-5 pb-5">
                {d?.message && !d.reviews.length ? (
                  <p className="py-6 text-center text-xs leading-relaxed text-rp-tlight">
                    {d.message}
                  </p>
                ) : null}

                {d?.reviews?.length ? (
                  <ul className="space-y-4">
                    {d.reviews.map((r, i) => (
                      <li
                        key={`${r.timestamp ?? ""}-${i}`}
                        className="rounded-lg border border-rp-border bg-white p-4 shadow-sm"
                      >
                        {/* Review header */}
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="inline-flex items-center gap-1.5 text-[13px] font-bold text-navy">
                            <UserCircle2 className="h-4 w-4 text-rp-tlight" />
                            {r.profile_name ?? "Google user"}
                          </span>
                          <span className="flex items-center gap-2 text-[11px] text-rp-tlight">
                            <StarRow rating={r.rating} />
                            {r.rating != null && (
                              <span className="font-semibold text-navy">{r.rating.toFixed(1)}</span>
                            )}
                            {r.time_ago
                              ? `· ${r.time_ago}`
                              : r.timestamp
                              ? `· ${r.timestamp}`
                              : ""}
                          </span>
                        </div>

                        {/* Review text */}
                        <p className="mt-2 text-[13px] leading-relaxed text-rp-tmid">
                          {r.review_text}
                        </p>

                        {/* AI response draft */}
                        <AiDraftBlock review={r} />
                      </li>
                    ))}
                  </ul>
                ) : !d?.message ? (
                  <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
                    <div className="rounded-full bg-rp-light p-3 text-[#72C219]">
                      <Star className="h-5 w-5" />
                    </div>
                    <div className="text-sm font-semibold text-navy">No reviews in this response</div>
                    <p className="max-w-md text-xs leading-relaxed text-rp-tlight">
                      Refine your business name and address on your profile, or connect GBP so we
                      can use your Google{" "}
                      <code className="rounded bg-rp-light px-1">place_id</code> for an exact match.
                    </p>
                  </div>
                ) : null}

                {d?.fetched_at ? (
                  <p className="mt-4 text-center text-[10px] text-rp-tlight">
                    Fetched {new Date(d.fetched_at).toLocaleString()}
                  </p>
                ) : null}
              </div>
            )}
          </Card>
        </div>

      </div>
    </>
  );
}

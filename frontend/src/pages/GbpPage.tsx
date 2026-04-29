import { useQuery } from "@tanstack/react-query";
import { Megaphone, MessageCircleQuestion, MapPin, ShieldCheck } from "lucide-react";

import { fetchGbpActivity } from "../api/gbp";
import { useAuthStore } from "../stores/authStore";
import { TopBar } from "../components/layout/TopBar";
import { Card, CardHeader } from "../components/ui/Card";

function EmptyGbp() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      <div className="rounded-full bg-rp-light p-3 text-[#72C219]">
        <MapPin className="h-6 w-6" />
      </div>
      <div className="text-sm font-semibold text-navy">No GBP activity yet</div>
      <p className="max-w-sm text-xs text-rp-tlight">
        Once your Google Business Profile is connected and the first post or optimization runs, activity
        will appear here. Weekly posts, Q&amp;A responses, and category updates are tracked automatically.
      </p>
    </div>
  );
}

export function GbpPage() {
  const token = useAuthStore((s) => s.accessToken);

  const activity = useQuery({
    queryKey: ["gbp", "activity", token],
    queryFn: fetchGbpActivity,
    enabled: Boolean(token),
  });

  const items = activity.data?.items ?? [];

  return (
    <>
      <TopBar
        title="GBP Optimiser"
        subtitle="Google Business Profile — weekly posts, Q&A, and health score"
      />
      <div className="flex-1 overflow-y-auto bg-rp-light px-7 py-6">
        {activity.isLoading ? (
          <p className="text-sm text-rp-tlight">Loading GBP activity…</p>
        ) : activity.isError ? (
          <p className="text-sm text-red-500">Failed to load GBP activity.</p>
        ) : null}

        <div className="mb-6 grid gap-4 sm:grid-cols-3">
          {[
            { label: "Weekly Posts", desc: "Auto-published every Monday", icon: Megaphone, status: "Coming soon" },
            { label: "Q&A Manager", desc: "AI-drafted responses to questions", icon: MessageCircleQuestion, status: "Coming soon" },
            { label: "GBP Health Score", desc: "Completeness check across all fields", icon: ShieldCheck, status: "Coming soon" },
          ].map((f) => (
            <div key={f.label} className="rounded-card border border-rp-border bg-white px-5 py-4 shadow-card">
              <div className="mb-2 inline-flex rounded-lg bg-[#72C219]/15 p-2 text-[#72C219]">
                <f.icon className="h-4 w-4" />
              </div>
              <div className="text-[13px] font-bold text-navy">{f.label}</div>
              <div className="mt-0.5 text-xs text-rp-tlight">{f.desc}</div>
              <div className="mt-3 inline-block rounded-full bg-rp-light px-2 py-0.5 text-[10px] font-semibold text-rp-tlight">
                {f.status}
              </div>
            </div>
          ))}
        </div>

        <Card>
          <CardHeader
            title="GBP Activity Feed"
            subtitle="Posts, Q&A responses, and optimization events"
          />
          {items.length === 0 ? (
            <EmptyGbp />
          ) : (
            <div className="divide-y divide-[#F0F4F9]">
              {items.map((item, i) => (
                <div key={i} className="flex items-start gap-3 px-5 py-3">
                  <div
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm"
                    style={{ background: "rgba(31,122,140,0.1)" }}
                  >
                    <MapPin className="h-4 w-4 text-teal" />
                  </div>
                  <div>
                    <p className="text-[13px] font-semibold text-navy capitalize">{item.type.replace(/_/g, " ")}</p>
                    <p className="text-xs text-rp-tlight">{item.description}</p>
                    <p className="mt-0.5 text-[11px] text-rp-tlight">
                      {new Date(item.occurred_at).toLocaleString("en-AU")}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-[12px] text-blue-800">
          <strong>GBP Optimisation roadmap:</strong> Connect your Google Business Profile to unlock weekly
          AI-generated posts, automated Q&amp;A responses, and a completeness health score that tracks your
          listing over time.
          {/* TODO: connect to GBP OAuth flow once client_integrations table is wired */}
        </div>
      </div>
    </>
  );
}

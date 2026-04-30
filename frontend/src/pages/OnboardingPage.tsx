import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, Globe2, LucideIcon, MapPin, Search } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { saveOnboarding } from "../api/onboarding";
import {
  connectWordPress,
  disconnectIntegration,
  fetchGbpProperties,
  fetchGa4Properties,
  fetchGoogleAuthUrl,
  fetchGscProperties,
  fetchIntegrationsStatus,
  selectGbpProperty,
  selectGa4Property,
  selectGscProperty,
} from "../api/integrations";
import { enqueueMapsScan } from "../api/scans";
import { useAuthStore } from "../stores/authStore";

/* ── City → metro_label mapper ──────────────────────────────────── */
const CITY_METRO_MAP: Record<string, string> = {
  sydney: "Sydney, NSW", "new south wales": "Sydney, NSW", nsw: "Sydney, NSW",
  melbourne: "Melbourne, VIC", victoria: "Melbourne, VIC", vic: "Melbourne, VIC",
  brisbane: "Brisbane, QLD", queensland: "Brisbane, QLD", qld: "Brisbane, QLD",
  perth: "Perth, WA", "western australia": "Perth, WA", wa: "Perth, WA",
  adelaide: "Adelaide, SA", "south australia": "Adelaide, SA", sa: "Adelaide, SA",
  "gold coast": "Gold Coast, QLD",
  canberra: "Canberra, ACT", act: "Canberra, ACT",
  hobart: "Hobart, TAS", tasmania: "Hobart, TAS", tas: "Hobart, TAS",
  darwin: "Darwin, NT", nt: "Darwin, NT",
};
function resolveMetroLabel(city: string): string {
  return CITY_METRO_MAP[city.trim().toLowerCase()] ?? `${city.trim()}, NSW`;
}

/* ── Integration metadata ────────────────────────────────────────── */
type OAuthType = "gsc" | "gbp" | "ga4";
interface IntgMeta {
  id:        string;
  icon:      LucideIcon;
  iconBg:    string;
  name:      string;
  desc:      string;
  oauthType: OAuthType | null; // null = WordPress (custom modal)
}
const INTEGRATIONS: IntgMeta[] = [
  { id:"gsc", icon:Search, iconBg:"#4285F4", name:"Google Search Console",   desc:"Provides actual keyword click data for your website",         oauthType:"gsc" },
  { id:"gbp", icon:MapPin, iconBg:"#34A853", name:"Google Business Profile",  desc:"Your Google Maps listing \u2014 required for GBP automation",  oauthType:"gbp" },
  /* id must match backend rp_integrations.type ("wordpress") for status + disconnect */
  { id:"wordpress", icon:Globe2, iconBg:"#21759B", name:"WordPress Website", desc:"Allows RankPilot to publish suburb pages automatically", oauthType:null },
  { id:"ga4", icon:BarChart3, iconBg:"#F9AB00", name:"Google Analytics 4 (GA4)", desc:"Shows actual website visitor numbers in your monthly report",  oauthType:"ga4" },
];

const SERP_THEME = {
  navy: "#0F2343",
  accent: "#72C219",
  textMuted: "#8092A7",
  textMid: "#4D6078",
  border: "#DDE6D1",
  surface: "#F6F9F2",
};

/* ── Step bar ────────────────────────────────────────────────────── */
function StepBar({ current }: { current: 1 | 2 | 3 }) {
  const STEPS = [
    { n: 1 as const, label: "Business" },
    { n: 2 as const, label: "Connect"  },
    { n: 3 as const, label: "Done!"    },
  ];
  return (
    <div style={{ display:"flex", marginBottom:28 }}>
      {STEPS.map((s, i) => {
        const done = s.n < current, active = s.n === current;
        return (
          <div key={s.n} style={{ flex:1, textAlign:"center", position:"relative" }}>
            {i < STEPS.length - 1 && (
              <div style={{ position:"absolute", top:14, left:"60%", width:"80%", height:2, background:SERP_THEME.border, zIndex:0 }} />
            )}
            <div style={{ width:28, height:28, borderRadius:"50%", background:done?"#5AAA2E":active?SERP_THEME.accent:SERP_THEME.border, color:done||active?"#fff":SERP_THEME.textMuted, fontSize:12, fontWeight:700, display:"flex", alignItems:"center", justifyContent:"center", margin:"0 auto 6px", position:"relative", zIndex:1 }}>
              {done ? "\u2713" : s.n}
            </div>
            <div style={{ fontSize:10, fontWeight:600, color:active?SERP_THEME.accent:SERP_THEME.textMuted }}>{s.label}</div>
          </div>
        );
      })}
    </div>
  );
}

/* ── Form field ──────────────────────────────────────────────────── */
function Field({ label, hint, children }: { label:string; hint?:string; children:React.ReactNode }) {
  return (
    <div style={{ marginBottom:14 }}>
      <label style={{ display:"block", fontSize:11, fontWeight:700, color:SERP_THEME.textMid, textTransform:"uppercase", letterSpacing:"0.6px", marginBottom:5 }}>{label}</label>
      {children}
      {hint && <p style={{ fontSize:10, color:SERP_THEME.textMuted, marginTop:4 }}>{hint}</p>}
    </div>
  );
}
const INPUT: React.CSSProperties = { width:"100%", border:`1px solid ${SERP_THEME.border}`, borderRadius:8, padding:"9px 12px", fontSize:13, color:SERP_THEME.navy, outline:"none", boxSizing:"border-box", fontFamily:"inherit", background:"#fff" };
const CTA_BASE: React.CSSProperties = { width:"100%", padding:11, fontSize:13, fontWeight:700, borderRadius:9, background:SERP_THEME.accent, color:"#fff", border:"none", cursor:"pointer", marginTop:10 };

/* ── WordPress modal ─────────────────────────────────────────────── */
function WpPasswordToggle({ visible, onToggle }: { visible: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      aria-label={visible ? "Hide password" : "Show password"}
      onClick={onToggle}
      style={{
        position: "absolute",
        right: 8,
        top: "50%",
        transform: "translateY(-50%)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        width: 32,
        height: 32,
        padding: 0,
        border: "none",
        borderRadius: 6,
        background: "transparent",
        cursor: "pointer",
        color: "#4A5E78",
      }}
    >
      {visible ? (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
          <line x1="1" y1="1" x2="23" y2="23" />
        </svg>
      ) : (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      )}
    </button>
  );
}

function WpModal({ onClose, onConnected }: { onClose:()=>void; onConnected:()=>void }) {
  const [siteUrl,     setSiteUrl]     = useState("");
  const [username,    setUsername]    = useState("");
  const [appPassword, setAppPassword] = useState("");
  const [showAppPassword, setShowAppPassword] = useState(false);
  const [err,         setErr]         = useState("");
  const [busy,        setBusy]        = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      await connectWordPress({ site_url:siteUrl, username, app_password:appPassword });
      onConnected();
      onClose();
    } catch(ex) {
      setErr(ex instanceof Error ? ex.message : "Connection failed");
    } finally { setBusy(false); }
  }

  return (
    <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,0.45)", display:"flex", alignItems:"center", justifyContent:"center", zIndex:999 }}>
      <div style={{ background:"#fff", borderRadius:14, padding:32, width:"100%", maxWidth:420, boxShadow:"0 18px 42px rgba(15,35,67,0.22)" }}>
        <h3 style={{ fontSize:16, fontWeight:800, color:SERP_THEME.navy, marginBottom:4 }}>Connect WordPress</h3>
        <p style={{ fontSize:12, color:SERP_THEME.textMuted, marginBottom:20 }}>
          Go to <strong>WordPress Admin &rarr; Users &rarr; Profile &rarr; Application Passwords</strong>, create a password for "RankPilot", then paste it below.
          Use your <strong>site root URL</strong> (e.g. https://yoursite.com.au) — do not paste the /wp-admin address.
        </p>
        <form onSubmit={(e) => void submit(e)}>
          <Field label="WordPress Site URL" hint="Homepage URL only, not wp-admin — REST lives at /wp-json on the root.">
            <input required style={INPUT} placeholder="https://yoursite.com.au" value={siteUrl} onChange={e=>setSiteUrl(e.target.value)} />
          </Field>
          <Field label="WordPress Username">
            <input required style={INPUT} placeholder="admin" value={username} onChange={e=>setUsername(e.target.value)} />
          </Field>
          <Field label="Application Password" hint="From WP Admin → Users → Profile → Application Passwords. Spaces are OK.">
            <div style={{ position: "relative" }}>
              <input
                required
                style={{ ...INPUT, paddingRight: 44 }}
                type={showAppPassword ? "text" : "password"}
                autoComplete="off"
                placeholder="xxxx xxxx xxxx xxxx xxxx xxxx"
                value={appPassword}
                onChange={(e) => setAppPassword(e.target.value)}
              />
              <WpPasswordToggle visible={showAppPassword} onToggle={() => setShowAppPassword((v) => !v)} />
            </div>
          </Field>
          {err && <p style={{ color:"#DC2626", fontSize:12, marginBottom:8 }}>{err}</p>}
          <button type="submit" disabled={busy} style={{ ...CTA_BASE, marginTop:6, opacity:busy?0.6:1 }}>{busy?"Verifying…":"Connect WordPress"}</button>
          <button type="button" onClick={onClose} style={{ display:"block", width:"100%", marginTop:8, padding:8, fontSize:12, color:SERP_THEME.textMuted, background:"none", border:"none", cursor:"pointer" }}>Cancel</button>
        </form>
      </div>
    </div>
  );
}

function PropertyModal({
  title,
  items,
  busy,
  error,
  onSelect,
  onClose,
}: {
  title: string;
  items: { id: string; name: string; sub?: string }[];
  busy: boolean;
  error: string | null;
  onSelect: (id: string, name: string) => void;
  onClose: () => void;
}) {
  const [selected, setSelected] = useState<string>("");
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 999 }}>
      <div style={{ background: "#fff", borderRadius: 14, padding: 24, width: "100%", maxWidth: 760, boxShadow: "0 18px 42px rgba(15,35,67,0.22)" }}>
        <h3 style={{ fontSize: 18, fontWeight: 800, color: SERP_THEME.navy, marginBottom: 8 }}>{title}</h3>
        <p style={{ fontSize: 12, color: SERP_THEME.textMuted, marginBottom: 12 }}>Select the correct property for this business.</p>
        <div style={{ border: `1px solid ${SERP_THEME.border}`, borderRadius: 10, maxHeight: 340, overflowY: "auto" }}>
          {items.map((p) => (
            <label key={p.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", borderBottom: "1px solid #EEF2F8", cursor: "pointer" }}>
              <input type="radio" name="prop" checked={selected === p.id} onChange={() => setSelected(p.id)} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: SERP_THEME.navy }}>{p.name}</div>
                <div style={{ fontSize: 11, color: SERP_THEME.textMuted }}>{p.sub || p.id}</div>
              </div>
            </label>
          ))}
          {!items.length ? <div style={{ padding: 14, fontSize: 12, color: SERP_THEME.textMuted }}>No properties found.</div> : null}
        </div>
        {error ? <p style={{ marginTop: 8, fontSize: 12, color: "#DC2626" }}>{error}</p> : null}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
          <button type="button" onClick={onClose} style={{ padding: "8px 12px", fontSize: 12, borderRadius: 7, border: `1px solid ${SERP_THEME.border}`, background: "#fff", color: SERP_THEME.textMid }}>Cancel</button>
          <button
            type="button"
            disabled={!selected || busy}
            onClick={() => {
              const chosen = items.find((x) => x.id === selected);
              if (!chosen) return;
              onSelect(chosen.id, chosen.name);
            }}
            style={{ padding: "8px 12px", fontSize: 12, borderRadius: 7, border: "none", background: SERP_THEME.accent, color: "#fff", opacity: !selected || busy ? 0.6 : 1 }}
          >
            {busy ? "Saving..." : "Confirm Selection"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════ */
export function OnboardingPage() {
  const navigate           = useNavigate();
  const qc                 = useQueryClient();
  const token              = useAuthStore((s) => s.accessToken);
  const setNeedsOnboarding = useAuthStore((s) => s.setNeedsOnboarding);

  const [step,        setStep]       = useState<1|2|3>(1);
  const [businessUrl, setUrl]        = useState("");
  const [keyword,     setKeyword]    = useState("");
  const [city,        setCity]       = useState("");
  const [radius,      setRadius]     = useState("20");
  const [showWpModal, setShowWpModal]= useState(false);
  const [showGscModal, setShowGscModal] = useState(false);
  const [showGbpModal, setShowGbpModal] = useState(false);
  const [showGa4Modal, setShowGa4Modal] = useState(false);
  const popupRef = useRef<Window | null>(null);

  /* ── Load current connection status ── */
  const statusQ = useQuery({
    queryKey: ["integrations-status"],
    queryFn:  fetchIntegrationsStatus,
    enabled:  step === 2 && Boolean(token),
    refetchInterval: 3000, // poll while on step 2
  });
  const connStatus = statusQ.data ?? {};
  const gscSelected = Boolean(connStatus.gsc?.extra?.selected_property);
  const ga4Selected = Boolean(connStatus.ga4?.extra?.selected_property);
  const gscConnected = Boolean(connStatus.gsc?.connected);
  const ga4Connected = Boolean(connStatus.ga4?.connected);
  const requiredConnected = gscConnected && ga4Connected && gscSelected && ga4Selected;

  const gscPropsQ = useQuery({
    queryKey: ["gsc-properties"],
    queryFn: fetchGscProperties,
    enabled: showGscModal,
  });
  const gbpPropsQ = useQuery({
    queryKey: ["gbp-properties"],
    queryFn: fetchGbpProperties,
    enabled: showGbpModal,
  });
  const ga4PropsQ = useQuery({
    queryKey: ["ga4-properties"],
    queryFn: fetchGa4Properties,
    enabled: showGa4Modal,
  });

  /* ── Listen for OAuth popup postMessage ── */
  const handlePopupMsg = useCallback((evt: MessageEvent) => {
    const d = evt.data as { rankpilot_oauth?: boolean; type?: string; success?: boolean };
    if (!d?.rankpilot_oauth) return;
    if (d.success) {
      void qc.invalidateQueries({ queryKey: ["integrations-status"] });
      if (d.type === "gsc") setShowGscModal(true);
      if (d.type === "gbp") setShowGbpModal(true);
      if (d.type === "ga4") setShowGa4Modal(true);
    }
    popupRef.current = null;
  }, [qc]);

  useEffect(() => {
    window.addEventListener("message", handlePopupMsg);
    return () => window.removeEventListener("message", handlePopupMsg);
  }, [handlePopupMsg]);

  /* ── Mutations ── */
  const save = useMutation({
    mutationFn: saveOnboarding,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["me"] });
      await qc.invalidateQueries({ queryKey: ["dashboard"] });
      await qc.invalidateQueries({ queryKey: ["ranks"] });
      setStep(2);
    },
  });

  const scan = useMutation({
    mutationFn: () => enqueueMapsScan({ keyword, radius_km: Number(radius) || 25 }),
    onSuccess: (res: { job_id: string; status: string }) => {
      void navigate(`/loading-results?job=${res.job_id}`, { replace: true });
    },
  });

  const disconnect = useMutation({
    mutationFn: (type: string) => disconnectIntegration(type),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["integrations-status"] }),
  });
  const selectGsc = useMutation({
    mutationFn: (body: { property_id: string; property_name?: string }) => selectGscProperty(body),
    onSuccess: async () => {
      setShowGscModal(false);
      await qc.invalidateQueries({ queryKey: ["integrations-status"] });
    },
  });
  const selectGa4 = useMutation({
    mutationFn: (body: { property_id: string; property_name?: string }) => selectGa4Property(body),
    onSuccess: async () => {
      setShowGa4Modal(false);
      await qc.invalidateQueries({ queryKey: ["integrations-status"] });
    },
  });
  const selectGbp = useMutation({
    mutationFn: (body: { property_id: string; property_name?: string }) => selectGbpProperty(body),
    onSuccess: async () => {
      setShowGbpModal(false);
      await qc.invalidateQueries({ queryKey: ["integrations-status"] });
    },
  });

  if (!token) { void navigate("/login", { replace:true }); return null; }

  function goToDashboard() {
    setNeedsOnboarding(false);
    void qc.invalidateQueries({ queryKey: ["me"] });
    void navigate("/", { replace:true });
  }

  /* Open Google OAuth popup */
  async function openGoogleOAuth(type: OAuthType) {
    try {
      const { url } = await fetchGoogleAuthUrl(type);
      const w = 600, h = 700;
      const left = window.screenX + (window.outerWidth  - w) / 2;
      const top  = window.screenY + (window.outerHeight - h) / 2;
      popupRef.current = window.open(url, "rankpilot_oauth", `width=${w},height=${h},left=${left},top=${top},toolbar=no,menubar=no`);
    } catch (ex) {
      const msg = ex instanceof Error ? ex.message : "OAuth error";
      alert(msg.includes("GOOGLE_CLIENT_ID") ? "Google OAuth is not configured yet. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to backend/.env" : msg);
    }
  }

  /* ── RENDER ─────────────────────────────────────────────────────── */
  return (
    <div style={{
      minHeight:"100vh",
      backgroundColor: SERP_THEME.surface,
      backgroundImage:
        "radial-gradient(ellipse 80% 50% at 15% 0%, rgba(114,194,25,0.16) 0%, transparent 65%), " +
        "radial-gradient(ellipse 55% 45% at 85% 100%, rgba(114,194,25,0.08) 0%, transparent 65%)",
      display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", padding:"24px 16px"
    }}>
      {showWpModal && (
        <WpModal
          onClose={() => setShowWpModal(false)}
          onConnected={() => void qc.invalidateQueries({ queryKey:["integrations-status"] })}
        />
      )}
      {showGscModal && (
        <PropertyModal
          title="Select your website in Search Console"
          items={(gscPropsQ.data?.items ?? []).map((p: { property_id: string; property_name: string; property_type: string; permission_level: string }) => ({
            id: p.property_id,
            name: p.property_name,
            sub: `${p.property_type} · ${p.permission_level}`,
          }))}
          busy={selectGsc.isPending}
          error={
            gscPropsQ.isError
              ? (gscPropsQ.error as Error).message
              : selectGsc.isError
                ? (selectGsc.error as Error).message
                : null
          }
          onClose={() => setShowGscModal(false)}
          onSelect={(id, name) => void selectGsc.mutate({ property_id: id, property_name: name })}
        />
      )}
      {showGbpModal && (
        <PropertyModal
          title="Select your Google Business Profile location"
          items={(gbpPropsQ.data?.items ?? []).map((p: { property_id: string; property_name: string; account_name: string; address?: string }) => ({
            id: p.property_id,
            name: p.property_name,
            sub: [p.account_name, p.address].filter(Boolean).join(" · "),
          }))}
          busy={selectGbp.isPending}
          error={
            gbpPropsQ.isError
              ? (gbpPropsQ.error as Error).message
              : selectGbp.isError
                ? (selectGbp.error as Error).message
                : null
          }
          onClose={() => setShowGbpModal(false)}
          onSelect={(id, name) => void selectGbp.mutate({ property_id: id, property_name: name })}
        />
      )}
      {showGa4Modal && (
        <PropertyModal
          title="Select your GA4 Property"
          items={(ga4PropsQ.data?.items ?? []).map((p: { property_id: string; property_name: string; account_name: string }) => ({
            id: p.property_id,
            name: p.property_name,
            sub: p.account_name,
          }))}
          busy={selectGa4.isPending}
          error={
            ga4PropsQ.isError
              ? (ga4PropsQ.error as Error).message
              : selectGa4.isError
                ? (selectGa4.error as Error).message
                : null
          }
          onClose={() => setShowGa4Modal(false)}
          onSelect={(id, name) => void selectGa4.mutate({ property_id: id, property_name: name })}
        />
      )}

      {/* Brand */}
      <div style={{ textAlign:"center", marginBottom:24 }}>
        <div style={{ fontSize:24, fontWeight:900, letterSpacing:"-0.5px", color:SERP_THEME.navy }}>
          Rank<span style={{ color:SERP_THEME.accent }}>Pilot</span>
        </div>
        <div style={{ fontSize:11, color:SERP_THEME.textMuted, marginTop:2 }}>SEO Autopilot &mdash; powered by Traffic Radius</div>
      </div>

      {/* Card */}
      <div style={{ background:"#fff", borderRadius:16, padding:36, width:"100%", maxWidth:500, border:`1px solid ${SERP_THEME.border}`, boxShadow:"0 16px 42px rgba(15,35,67,0.10)" }}>
        <StepBar current={step} />

        {/* ══ STEP 1 — Business Details ══ */}
        {step === 1 && (
          <>
            <h2 style={{ fontSize:18, fontWeight:800, color:SERP_THEME.navy, marginBottom:6 }}>Tell us about your business</h2>
            <p style={{ fontSize:12, color:SERP_THEME.textMuted, marginBottom:20 }}>RankPilot uses this information to find your business on Google and start tracking your rankings.</p>
            <form onSubmit={(e)=>{ e.preventDefault(); save.mutate({ business_name: businessUrl.replace(/^https?:\/\//,"").replace(/^www\./,"").split(".")[0]??"", business_url:businessUrl.trim(), primary_keyword:keyword.trim(), metro_label:resolveMetroLabel(city), search_radius_km: Math.min(100, Math.max(5, Number(radius) || 25)) }); }}>
              <Field label="Business Website URL">
                <input type="text" required style={INPUT} placeholder="https://yourbusiness.com.au" value={businessUrl} onChange={e=>setUrl(e.target.value)} />
              </Field>
              <Field label="Primary Service (what you do)">
                <input type="text" required style={INPUT} placeholder="e.g. plumber, electrician, finance broker" value={keyword} onChange={e=>setKeyword(e.target.value)} />
              </Field>
              <Field label="Main City / Suburb">
                <input type="text" required style={INPUT} placeholder="e.g. Melbourne, Brisbane, Sydney" value={city} onChange={e=>setCity(e.target.value)} />
              </Field>
              <Field label="Service radius" hint="We scan suburbs inside this distance — categorised for reporting.">
                {(() => {
                  const BANDS = [
                    { label: "0–5 km (local block)",    max: 5  },
                    { label: "6–10 km (local)",          max: 10 },
                    { label: "11–15 km (suburb)",        max: 15 },
                    { label: "16–20 km (greater metro)", max: 20 },
                    { label: "21–25 km (city-wide)",     max: 25 },
                    { label: "26–30 km (regional)",      max: 30 },
                  ];
                  const pill = (label: string, max: number) => {
                    const active = Number(radius) === max;
                    return (
                      <button
                        key={max}
                        type="button"
                        onClick={() => setRadius(String(max))}
                        style={{
                          padding: "4px 10px",
                          borderRadius: 20,
                          border: active ? "none" : "1px solid #D1D5DB",
                          background: active ? "#72C219" : "#F9FAFB",
                          color: active ? "#fff" : "#374151",
                          fontSize: 12,
                          fontWeight: active ? 700 : 500,
                          cursor: "pointer",
                        }}
                      >
                        {label.split(" ")[0]}
                      </button>
                    );
                  };
                  return (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      <select
                        value={radius}
                        onChange={e => setRadius(e.target.value)}
                        style={{ ...INPUT, cursor: "pointer" }}
                      >
                        {BANDS.map(b => (
                          <option key={b.max} value={String(b.max)}>{b.label}</option>
                        ))}
                      </select>
                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                        {BANDS.map(b => pill(b.label, b.max))}
                      </div>
                    </div>
                  );
                })()}
              </Field>
              {save.isError && <p style={{ color:"#DC2626", fontSize:12, marginBottom:8 }}>{(save.error as Error).message}</p>}
              <button type="submit" disabled={save.isPending||!businessUrl.trim()||!keyword.trim()||!city.trim()} style={{ ...CTA_BASE, opacity:save.isPending?0.6:1 }}>
                {save.isPending ? "Saving\u2026" : "Continue \u2192 Connect Accounts"}
              </button>
            </form>
          </>
        )}

        {/* ══ STEP 2 — Connect Accounts ══ */}
        {step === 2 && (
          <>
            <h2 style={{ fontSize:18, fontWeight:800, color:SERP_THEME.navy, marginBottom:4 }}>Connect your accounts</h2>
            <p style={{ fontSize:12, color:SERP_THEME.textMuted, marginBottom:20 }}>Each connection unlocks more features. You can connect them later but connecting now gives you full data from Day 1.</p>

            <div style={{ marginBottom:14 }}>
              {INTEGRATIONS.map((intg) => {
                const isConn = Boolean(connStatus[intg.id]?.connected);
                const selectedProperty = connStatus[intg.id]?.extra?.selected_property;
                return (
                  <div key={intg.id} style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"12px 14px", border:`1px solid ${SERP_THEME.border}`, borderRadius:9, marginBottom:10 }}>
                    {/* Left: icon + text */}
                    <div style={{ display:"flex", alignItems:"center", gap:12 }}>
                      <div style={{ width:32, height:32, borderRadius:8, background:intg.iconBg, color:"#fff", display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0 }}>
                        <intg.icon size={16} strokeWidth={2.25} />
                      </div>
                      <div>
                        <div style={{ fontSize:13, fontWeight:600, color:SERP_THEME.navy }}>{intg.name}</div>
                        <div style={{ fontSize:10, color:SERP_THEME.textMuted }}>{intg.desc}</div>
                        {(intg.id === "gsc" || intg.id === "gbp" || intg.id === "ga4") && selectedProperty ? (
                          <div style={{ marginTop: 2, fontSize: 10, fontWeight: 700, color: "#15803D" }}>
                            Selected: {String(selectedProperty)}
                          </div>
                        ) : intg.id === "wordpress" && connStatus.wordpress?.extra?.site_url ? (
                          <div style={{ marginTop: 2, fontSize: 10, fontWeight: 700, color: "#15803D" }}>
                            Site: {String(connStatus.wordpress.extra.site_url)}
                          </div>
                        ) : null}
                      </div>
                    </div>
                    {/* Right: connect / disconnect */}
                    {isConn ? (
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        {(intg.id === "gsc" || intg.id === "gbp" || intg.id === "ga4") ? (
                          <button
                            type="button"
                            style={{ padding:"5px 10px", borderRadius:6, fontSize:11, fontWeight:700, border:`1px solid ${SERP_THEME.border}`, cursor:"pointer", background:"#fff", color:"#2E4F7F", whiteSpace:"nowrap" }}
                            onClick={() => {
                              if (intg.id === "gsc") setShowGscModal(true);
                              if (intg.id === "gbp") setShowGbpModal(true);
                              if (intg.id === "ga4") setShowGa4Modal(true);
                            }}
                          >
                            {selectedProperty ? "Change Property" : "Select Property"}
                          </button>
                        ) : null}
                        <button type="button"
                          style={{ padding:"5px 12px", borderRadius:6, fontSize:11, fontWeight:700, border:"none", cursor:"pointer", background:"#DCFCE7", color:"#15803D", whiteSpace:"nowrap" }}
                          onClick={()=>void disconnect.mutate(intg.id)}
                        >
                          {"\u2713 Connected"}
                        </button>
                      </div>
                    ) : (
                      <button type="button"
                        style={{ padding:"5px 12px", borderRadius:6, fontSize:11, fontWeight:700, border:"none", cursor:"pointer", background:SERP_THEME.accent, color:"#fff", whiteSpace:"nowrap" }}
                        onClick={() => {
                          if (intg.oauthType) void openGoogleOAuth(intg.oauthType);
                          else setShowWpModal(true);
                        }}
                      >
                        Connect
                      </button>
                    )}
                  </div>
                );
              })}
            </div>

            <button
              type="button"
              disabled={scan.isPending || !requiredConnected}
              style={{ ...CTA_BASE, opacity: (scan.isPending || !requiredConnected) ? 0.6 : 1 }}
              onClick={() => void scan.mutate()}
            >
              {scan.isPending ? "Starting scan\u2026" : "Start My First Scan \u2192"}
            </button>
            {!requiredConnected ? (
              <p style={{ marginTop: 8, fontSize: 11, color: "#B45309" }}>
                Connect GSC + GA4 and select the correct property in each before loading the results dashboard.
              </p>
            ) : null}
            {scan.isError ? (
              <p style={{ marginTop: 8, fontSize: 11, color: "#DC2626" }}>
                {(scan.error as Error).message}
              </p>
            ) : null}
            <button type="button" style={{ display:"block", width:"100%", marginTop:8, padding:8, fontSize:12, fontWeight:600, color:SERP_THEME.textMuted, background:"none", border:"none", cursor:"pointer" }} onClick={()=>setStep(3)}>
              Skip for now &mdash; connect later
            </button>
          </>
        )}

        {/* ══ STEP 3 — Done! ══ */}
        {step === 3 && (
          <div style={{ textAlign:"center" }}>
            <div style={{ fontSize:48, marginBottom:16 }}>{"\uD83C\uDF89"}</div>
            <h2 style={{ fontSize:22, fontWeight:800, color:SERP_THEME.navy, marginBottom:8 }}>You&apos;re all set!</h2>
            <p style={{ fontSize:13, color:SERP_THEME.textMid, marginBottom:4 }}>Your first Maps ranking scan has been queued.</p>
            <p style={{ fontSize:12, color:SERP_THEME.textMuted, marginBottom:24 }}>Rankings and your visibility score will appear on the dashboard in 2&ndash;4 minutes once DataForSEO finishes checking each suburb.</p>

            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginBottom:24, textAlign:"left" }}>
              {[
                { label:"Business URL", val:businessUrl||"\u2014" },
                { label:"Keyword",      val:keyword||"\u2014"     },
                { label:"City",         val:city||"\u2014"        },
                { label:"Radius",       val:`${radius} km`        },
              ].map((d) => (
                <div key={d.label} style={{ background:"#F0FDF4", border:"1px solid #DCFCE7", borderRadius:8, padding:"10px 12px" }}>
                  <div style={{ fontSize:9, fontWeight:700, textTransform:"uppercase", letterSpacing:"0.6px", color:"#15803D", marginBottom:3 }}>{d.label}</div>
                  <div style={{ fontSize:11, fontWeight:600, color:SERP_THEME.navy, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{d.val}</div>
                </div>
              ))}
            </div>

            <button type="button" style={{ ...CTA_BASE, opacity:1 }} onClick={goToDashboard}>Go to Dashboard &rarr;</button>
          </div>
        )}
      </div>

      <p style={{ marginTop:20, fontSize:11, color:SERP_THEME.textMuted }}>
        Want to skip?{" "}
        <button type="button" style={{ fontWeight:600, color:SERP_THEME.accent, background:"none", border:"none", cursor:"pointer", fontSize:11 }} onClick={goToDashboard}>
          Go to Dashboard &rarr;
        </button>
      </p>
    </div>
  );
}

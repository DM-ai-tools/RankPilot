import { useEffect, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { loginRequest } from "../api/auth";
import { fetchMeForAuth } from "../api/onboarding";
import { Button } from "../components/ui/Button";
import { isProfileComplete, postLoginPath } from "../lib/profile";
import { useAuthStore } from "../stores/authStore";

type LocState = { from?: string };

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const setToken = useAuthStore((s) => s.setAccessToken);
  const existing = useAuthStore((s) => s.accessToken);
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const from = (location.state as LocState | null)?.from ?? "/";

  useEffect(() => {
    if (pending || !existing) return;
    let cancelled = false;
    void (async () => {
      try {
        const me = await fetchMeForAuth();
        if (cancelled) return;
        void navigate(postLoginPath(isProfileComplete(me), from), { replace: true });
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load profile — is the backend running?");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [existing, from, navigate, pending]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setPending(true);
    try {
      const res = await loginRequest(username, password);
      setToken(res.access_token);
      const me = await fetchMeForAuth();
      void navigate(postLoginPath(isProfileComplete(me), from), { replace: true });
    } catch (e2) {
      setToken(null);
      setErr(e2 instanceof Error ? e2.message : "Sign-in failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-rp-shell px-4 py-10">
      <div className="mb-6 text-center">
        <div className="text-3xl font-extrabold tracking-tight text-neutral-900">
          Rank<span className="text-brand-400">Pilot</span>
        </div>
        <p className="mt-1 text-sm text-neutral-500">Growth OS for local businesses</p>
      </div>

      <form
        onSubmit={(e) => void onSubmit(e)}
        className="w-full max-w-lg rounded-xl border border-neutral-200 bg-white p-6 shadow-lg sm:p-7"
      >
        <div className="mb-5 flex flex-col items-center text-center">
          <img
            src="/Traffic-Radius-Logo.webp"
            alt="Traffic Radius"
            className="mb-3 h-auto w-full max-w-[190px] object-contain"
          />
          <h1 className="text-[20px] font-extrabold leading-none tracking-tight text-navy sm:text-[20px]">
            Sign in
          </h1>
          <p className="mt-2 text-[13px] font-medium text-rp-tmid">
            Sign in to open your dashboard. New accounts complete business setup on the next screen.
          </p>
        </div>

        <label className="block text-[12px] font-bold uppercase tracking-wide text-rp-tlight">Username</label>
        <input
          type="text"
          autoComplete="username"
          className="mt-2 w-full rounded-xl border border-rp-border px-4 py-2.5 text-[14px] font-semibold text-navy outline-none ring-[#72C219]/30 transition focus:ring-2"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />

        <label className="mt-4 block text-[12px] font-bold uppercase tracking-wide text-rp-tlight">
          Password
        </label>
        <div className="relative mt-2">
          <input
            type={showPassword ? "text" : "password"}
            autoComplete="current-password"
            className="w-full rounded-xl border border-rp-border px-4 py-2.5 pr-12 text-[14px] font-semibold text-navy outline-none ring-[#72C219]/30 transition focus:ring-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="admin123"
          />
          <button
            type="button"
            onClick={() => setShowPassword((v) => !v)}
            className="absolute right-2.5 top-1/2 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-sm bg-neutral-50 text-neutral-600 hover:bg-brand-50 hover:text-brand-600"
            aria-label={showPassword ? "Hide password" : "Show password"}
          >
            {showPassword ? <EyeOff className="h-4.5 w-4.5" /> : <Eye className="h-4.5 w-4.5" />}
          </button>
        </div>

        {err ? <p className="mt-4 text-sm text-red-600">{err}</p> : null}

        <Button
          type="submit"
          className="mt-6 h-[46px] w-full rounded-xl bg-[#72C219] text-[16px] font-extrabold text-white hover:bg-[#5FA814]"
          disabled={pending}
        >
          {pending ? "Signing in..." : "Sign in"}
        </Button>
      </form>

      <Link
        to="/onboarding"
        state={{ from: "/onboarding" }}
        className="mt-6 text-sm font-semibold text-[#72C219] hover:underline"
      >
        New here? Onboarding →
      </Link>

      <p className="mt-8 text-center text-[11px] text-rp-tlight">
        By signing in you agree to our{" "}
        <Link to="/privacy" className="font-medium text-rp-tmid underline-offset-2 hover:underline">
          Privacy Policy
        </Link>
        .
      </p>
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import { Navigate, Outlet } from "react-router-dom";

import { formatApiError } from "../api/client";
import { fetchMeForAuth } from "../api/onboarding";
import { isProfileComplete } from "../lib/profile";
import { useAuthStore } from "../stores/authStore";

/**
 * Blocks the main app until the tenant profile has required business fields.
 * Uses live /me data — not a session flag that can go stale in sessionStorage.
 */
export function RequireOnboarded() {
  const token = useAuthStore((s) => s.accessToken);

  const meQ = useQuery({
    queryKey: ["me", "auth-gate", token],
    queryFn: fetchMeForAuth,
    enabled: Boolean(token),
    staleTime: 30_000,
    retry: 1,
  });

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  if (meQ.isPending && !meQ.data) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#EDF4DD] text-sm font-semibold text-navy">
        Loading your profile…
      </div>
    );
  }

  if (meQ.isError) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-[#EDF4DD] px-4 text-center">
        <p className="text-sm font-semibold text-navy">Could not load your profile</p>
        <p className="max-w-md text-xs text-rp-tmid">{formatApiError(meQ.error)}</p>
        <button
          type="button"
          className="rounded-lg bg-[#72C219] px-4 py-2 text-sm font-bold text-white"
          onClick={() => void meQ.refetch()}
        >
          Retry
        </button>
      </div>
    );
  }

  if (!isProfileComplete(meQ.data)) {
    return <Navigate to="/onboarding" replace />;
  }

  return <Outlet />;
}

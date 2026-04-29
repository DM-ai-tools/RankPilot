import { Navigate, Outlet } from "react-router-dom";

import { useAuthStore } from "../stores/authStore";

/**
 * After every fresh login `needsOnboarding` is true.
 * The user must pass through the onboarding wizard and click
 * "Go to Dashboard" (which sets it to false) before they can
 * reach the main app — even if the DB already has their data.
 */
export function RequireOnboarded() {
  const needsOnboarding = useAuthStore((s) => s.needsOnboarding);

  if (needsOnboarding) {
    return <Navigate to="/onboarding" replace />;
  }

  return <Outlet />;
}

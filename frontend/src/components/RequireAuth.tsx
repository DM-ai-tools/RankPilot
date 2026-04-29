import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuthStore } from "../stores/authStore";

export function RequireAuth() {
  const token = useAuthStore((s) => s.accessToken);
  const loc = useLocation();
  if (!token) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }
  return <Outlet />;
}

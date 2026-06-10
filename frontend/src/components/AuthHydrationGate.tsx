import { useEffect, useState } from "react";

import { useAuthStore } from "../stores/authStore";

/** Wait for sessionStorage auth rehydrate before routing (avoids blank /login flash). */
export function AuthHydrationGate({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(() => useAuthStore.persist.hasHydrated());

  useEffect(() => {
    if (useAuthStore.persist.hasHydrated()) {
      setReady(true);
      return;
    }
    const unsub = useAuthStore.persist.onFinishHydration(() => setReady(true));
    const t = window.setTimeout(() => setReady(true), 1500);
    return () => {
      unsub();
      window.clearTimeout(t);
    };
  }, []);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#EDF4DD] text-sm font-semibold text-navy">
        Loading…
      </div>
    );
  }

  return <>{children}</>;
}

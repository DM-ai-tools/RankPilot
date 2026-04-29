import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

type AuthState = {
  accessToken: string | null;
  /** True after login, until the user completes the onboarding wizard this session. */
  needsOnboarding: boolean;
  setAccessToken: (token: string | null) => void;
  setNeedsOnboarding: (v: boolean) => void;
};

/**
 * sessionStorage: token is wiped when the browser closes, forcing re-login.
 * needsOnboarding: set by LoginPage from /me (incomplete profile → onboarding).
 * Do not tie to setAccessToken — that forced every login through onboarding and blocked the dashboard.
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken:        null,
      needsOnboarding:    true,
      setAccessToken:     (token) => set({ accessToken: token }),
      setNeedsOnboarding: (v) => set({ needsOnboarding: v }),
    }),
    {
      name:    "rankpilot-auth",
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
);

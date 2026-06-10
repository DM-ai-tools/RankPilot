import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

type AuthState = {
  accessToken: string | null;
  setAccessToken: (token: string | null) => void;
};

/**
 * sessionStorage: token is wiped when the browser closes.
 * Onboarding gate comes from GET /me (see RequireOnboarded), not a persisted flag.
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      setAccessToken: (token) => set({ accessToken: token }),
    }),
    {
      name: "rankpilot-auth",
      version: 2,
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({ accessToken: state.accessToken }),
    },
  ),
);

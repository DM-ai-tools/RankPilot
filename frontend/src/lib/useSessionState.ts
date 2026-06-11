import { useEffect, useState } from "react";

/**
 * Like useState, but the value survives unmount (e.g. tab switches) by
 * mirroring into sessionStorage. Cleared when the browser tab closes.
 */
export function useSessionState(
  key: string,
  initial: string,
): [string, (v: string) => void] {
  const [value, setValue] = useState<string>(() => {
    try {
      const stored = sessionStorage.getItem(key);
      if (stored !== null) return stored;
    } catch {
      // sessionStorage unavailable — fall back to plain state
    }
    return initial;
  });

  useEffect(() => {
    try {
      sessionStorage.setItem(key, value);
    } catch {
      // ignore
    }
  }, [key, value]);

  return [value, setValue];
}

import type { ClientProfile } from "../api/onboarding";

export function isProfileComplete(me: ClientProfile | undefined | null): boolean {
  if (!me) return false;
  return Boolean(
    me.business_name?.trim() &&
      me.business_url?.trim() &&
      me.primary_keyword?.trim() &&
      me.metro_label?.trim(),
  );
}

export function postLoginPath(complete: boolean, from: string): string {
  if (!complete) return "/onboarding";
  if (from && from !== "/login") return from;
  return "/";
}

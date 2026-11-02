const RETURN_URL_KEY = "martins_attendance_return_url";

function launchEndpoint() {
  const configured = (
    import.meta.env.VITE_API_URL ||
    import.meta.env.VITE_API_BASE_URL ||
    ""
  ).replace(/\/$/, "");

  if (!configured) return "/api/auth/martins-launch";
  return `${configured.endsWith("/api") ? configured : `${configured}/api`}/auth/martins-launch`;
}

export async function consumeMartinsLaunch(token) {
  const response = await fetch(launchEndpoint(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "Unable to open Attendance from Martins System.");
  }

  if (payload.main_app_url) {
    window.sessionStorage.setItem(RETURN_URL_KEY, payload.main_app_url);
  }

  return payload;
}

export function returnToMartinsIfLaunched() {
  const returnUrl = window.sessionStorage.getItem(RETURN_URL_KEY);
  window.sessionStorage.removeItem(RETURN_URL_KEY);

  if (!returnUrl) return false;
  window.location.assign(returnUrl);
  return true;
}

export function profileSwitchUrl(mainAppUrl) {
  const fallback = 'https://martinssystem.co.za';
  try {
    const origin = new URL(mainAppUrl || fallback);
    if (origin.protocol !== 'https:' && !(origin.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(origin.hostname))) {
      return `${fallback}/profiles?module=attendance`;
    }
    const url = new URL('/profiles', origin);
    url.searchParams.set('module', 'attendance');
    return url.toString();
  } catch {
    return `${fallback}/profiles?module=attendance`;
  }
}

export function getProfileSwitchUrl() {
  try { return profileSwitchUrl(window.sessionStorage.getItem(RETURN_URL_KEY)); }
  catch { return profileSwitchUrl(); }
}

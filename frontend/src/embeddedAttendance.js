const MAIN_HOSTS = new Set(['martinssystem.co.za', 'www.martinssystem.co.za', 'martins-unified-system.onrender.com']);

export function embeddedParentOrigin() {
  try {
    if (window.parent === window || new URLSearchParams(window.location.search).get('embedded') !== '1') return '';
    const url = new URL(new URLSearchParams(window.location.search).get('parent_origin'));
    if ((url.protocol === 'https:' && MAIN_HOSTS.has(url.hostname)) ||
        (url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) return url.origin;
  } catch {}
  return '';
}

export function notifyAttendanceParent(type, extra = {}) {
  const origin = embeddedParentOrigin();
  if (origin) window.parent.postMessage({type, ...extra}, origin);
}

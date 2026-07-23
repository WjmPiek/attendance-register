from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont

root = Path('/mnt/data/pwa_work/frontend')
public = root/'public'

# Update manifest for installable mobile/desktop PWA
manifest = {
  "name": "ATTENDANCE",
  "short_name": "ATTENDANCE",
  "description": "ATTENDANCE",
  "id": "/",
  "start_url": "/?source=pwa",
  "scope": "/",
  "display": "standalone",
  "display_override": ["standalone", "minimal-ui"],
  "orientation": "portrait-primary",
  "background_color": "#00000000",
  "theme_color": "#9b6bd3",
  "categories": ["business", "productivity"],
  "icons": [
    {"src": "/icon-72.png", "sizes": "72x72", "type": "image/png", "purpose": "any"},
    {"src": "/icon-96.png", "sizes": "96x96", "type": "image/png", "purpose": "any"},
    {"src": "/icon-128.png", "sizes": "128x128", "type": "image/png", "purpose": "any"},
    {"src": "/icon-144.png", "sizes": "144x144", "type": "image/png", "purpose": "any"},
    {"src": "/icon-152.png", "sizes": "152x152", "type": "image/png", "purpose": "any"},
    {"src": "/icon-180.png", "sizes": "180x180", "type": "image/png", "purpose": "any"},
    {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
    {"src": "/icon-384.png", "sizes": "384x384", "type": "image/png", "purpose": "any maskable"},
    {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    {"src": "/icon-1024.png", "sizes": "1024x1024", "type": "image/png", "purpose": "any maskable"}
  ],
  "shortcuts": [
    {"name": "Mobile Sign In", "short_name": "Sign In", "url": "/?tab=attendance", "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"}]},
    {"name": "Payslips", "short_name": "Payslips", "url": "/?tab=payslips", "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"}]}
  ]
}
(public/'manifest.webmanifest').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

# Update index metadata so browsers detect install app and iOS Add to Home Screen uses ATTENDANCE.
index = root/'index.html'
index.write_text('''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <title>ATTENDANCE</title>
    <meta name="description" content="ATTENDANCE" />
    <meta name="theme-color" content="#9b6bd3" />
    <meta name="background-color" content="transparent" />
    <meta name="mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-title" content="ATTENDANCE" />
    <meta name="apple-mobile-web-app-status-bar-style" content="default" />
    <link rel="manifest" href="/manifest.webmanifest" />
    <link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png" />
    <link rel="icon" type="image/png" sizes="512x512" href="/icon-512.png" />
    <link rel="apple-touch-icon" sizes="180x180" href="/icon-180.png" />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
''', encoding='utf-8')

# Generate transparent app icons using existing logo and ATTENDANCE text.
logo = Image.open(public/'logo.png').convert('RGBA')
# Crop transparent/white-ish excess by alpha only if available; otherwise keep entire logo.
alpha_bbox = logo.getbbox()
if alpha_bbox:
    logo = logo.crop(alpha_bbox)

font_paths = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf'
]
font_path = next((p for p in font_paths if Path(p).exists()), None)

def fit_font(draw, text, max_width, max_height):
    size = max(10, max_height)
    while size > 8:
        font = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
        bbox = draw.textbbox((0,0), text, font=font)
        if bbox[2]-bbox[0] <= max_width and bbox[3]-bbox[1] <= max_height:
            return font
        size -= 2
    return ImageFont.load_default()

def make_icon(size):
    img = Image.new('RGBA', (size, size), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    pad = int(size * 0.10)
    logo_max_w = size - 2*pad
    logo_max_h = int(size * 0.48)
    scale = min(logo_max_w / logo.width, logo_max_h / logo.height)
    lw, lh = max(1, int(logo.width*scale)), max(1, int(logo.height*scale))
    lg = logo.resize((lw, lh), Image.Resampling.LANCZOS)
    img.alpha_composite(lg, ((size-lw)//2, int(size*0.12)))
    text = 'ATTENDANCE'
    font = fit_font(draw, text, int(size*0.82), int(size*0.12))
    tb = draw.textbbox((0,0), text, font=font)
    tw, th = tb[2]-tb[0], tb[3]-tb[1]
    tx = (size - tw)//2
    ty = int(size*0.68)
    # subtle light stroke for readability on any wallpaper while staying transparent
    stroke = max(1, size//128)
    draw.text((tx, ty), text, font=font, fill=(45,40,56,255), stroke_width=stroke, stroke_fill=(255,255,255,230))
    return img

for size in [72,96,128,144,152,180,192,384,512,1024]:
    make_icon(size).save(public/f'icon-{size}.png')
# favicon from 192
make_icon(64).save(public/'favicon.ico')
# splash transparent-ish fallback
make_icon(512).save(public/'splash.png')

# Service worker references real files and avoids caching API/doc protected responses.
sw = public/'service-worker.js'
sw.write_text('''const CACHE_NAME = 'attendance-pwa-v2';
const APP_SHELL = [
  '/',
  '/index.html',
  '/manifest.webmanifest',
  '/favicon.ico',
  '/icon-192.png',
  '/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).catch(() => null)
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.pathname.startsWith('/api') || url.pathname.includes('/download') || url.pathname.includes('/view')) return;

  event.respondWith(
    fetch(request).then((response) => {
      if (response && response.ok && response.type === 'basic') {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => null);
      }
      return response;
    }).catch(() => caches.match(request).then((cached) => cached || caches.match('/index.html')))
  );
});
''', encoding='utf-8')

# Update install prompt text to use ATTENDANCE label.
install = root/'src/components/InstallPrompt.jsx'
if install.exists():
    text = install.read_text(encoding='utf-8')
    text = text.replace('Install Attendance', 'Install ATTENDANCE')
    text = text.replace('Desktop and mobile app mode ready', 'Install on mobile or desktop')
    text = text.replace('alt="Attendance logo"', 'alt="ATTENDANCE logo"')
    install.write_text(text, encoding='utf-8')

print('[OK] PWA manifest, metadata, icons and service worker updated')

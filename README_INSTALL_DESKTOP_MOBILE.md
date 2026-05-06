# Attendance Register Platform - Desktop and Mobile Install

This package is prepared as an installable web app (PWA) with a branded logo, light grey/lilac theme, glass-effect buttons, and sidebar tabs.

## Desktop install
1. Start the backend and frontend.
2. Open the frontend URL in Chrome or Edge.
3. Click **Install App** in the sidebar/top bar, or click the install icon in the browser address bar.
4. The platform opens as a desktop app window with the Attendance logo.

## Mobile install
### Android
1. Open the frontend URL in Chrome.
2. Tap **Install App** if prompted, or open the browser menu and choose **Add to Home screen**.
3. The platform is added to the home screen with the Attendance logo.

### iPhone / iPad
1. Open the frontend URL in Safari.
2. Tap **Share**.
3. Tap **Add to Home Screen**.
4. The platform is added to the home screen with the Attendance logo.

## Production note
Install prompts require HTTPS, except on localhost. Deploy the frontend behind HTTPS for real mobile/desktop installation.

## Included frontend changes
- `public/logo.svg` branded app logo
- `public/manifest.webmanifest` desktop/mobile install manifest
- `public/service-worker.js` app shell cache
- service worker registration in `src/main.jsx`
- install prompt component in `src/components/InstallPrompt.jsx`
- light grey/lilac glass UI theme in `src/styles.css`
- sidebar tab layout in `src/pages/DashboardPage.jsx`

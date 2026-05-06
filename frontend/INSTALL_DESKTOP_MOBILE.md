# Martins Attendance Register - Desktop and Mobile Install

## Frontend web/PWA
```bash
cd frontend
npm install
npm run build
npm run preview
```

## Windows .exe installer
Build on Windows for best results:
```powershell
cd frontend
powershell -ExecutionPolicy Bypass -File scripts/build-windows.ps1
```
Output: `frontend/dist-electron/`.

## Android APK
Requires Android Studio SDK + Java 17+.
```bash
cd frontend
npm install
npm run build
npx cap add android
npx cap sync android
cd android
./gradlew assembleDebug
```
Output: `frontend/android/app/build/outputs/apk/debug/app-debug.apk`.

## Icons and splash
The Martins logo is installed at `frontend/public/logo.png`.
Generated icons and splash are in `frontend/public/`, `frontend/android-assets/`, and `frontend/ios-assets/`.

## API URL
Set your production API before building:
```bash
VITE_API_BASE_URL=https://your-domain.com/api npm run build
```

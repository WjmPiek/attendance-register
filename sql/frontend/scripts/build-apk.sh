#!/usr/bin/env bash
set -euo pipefail
npm install
npm run build
npx cap sync android
cd android
./gradlew assembleDebug
printf '\nAPK created at android/app/build/outputs/apk/debug/app-debug.apk\n'

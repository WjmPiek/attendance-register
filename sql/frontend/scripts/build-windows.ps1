$ErrorActionPreference = "Stop"
npm install
npm run build
npm run dist:win
Write-Host "Windows installer created in dist-electron/"

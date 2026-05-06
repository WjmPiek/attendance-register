import { useEffect, useState } from 'react'

function platformHelp() {
  const ua = navigator.userAgent || ''
  if (/iphone|ipad|ipod/i.test(ua)) return 'On iPhone/iPad: tap Share, then Add to Home Screen.'
  if (/android/i.test(ua)) return 'On Android: tap Install when prompted, or open browser menu and choose Add to Home screen.'
  return 'On desktop: use the Install button in Chrome/Edge, or the install icon in the address bar.'
}

export default function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState(null)
  const [installed, setInstalled] = useState(false)

  useEffect(() => {
    const beforeInstall = (event) => {
      event.preventDefault()
      setDeferredPrompt(event)
    }
    const appInstalled = () => {
      setInstalled(true)
      setDeferredPrompt(null)
    }
    window.addEventListener('beforeinstallprompt', beforeInstall)
    window.addEventListener('appinstalled', appInstalled)
    setInstalled(window.matchMedia?.('(display-mode: standalone)').matches || navigator.standalone === true)
    return () => {
      window.removeEventListener('beforeinstallprompt', beforeInstall)
      window.removeEventListener('appinstalled', appInstalled)
    }
  }, [])

  const install = async () => {
    if (!deferredPrompt) return
    deferredPrompt.prompt()
    await deferredPrompt.userChoice.catch(() => null)
    setDeferredPrompt(null)
  }

  return (
    <div className="install-card glass-card">
      <div className="brand-mini">
        <img src="/logo.png" alt="Attendance logo" />
        <div>
          <strong>Install Attendance</strong>
          <span>{installed ? 'Installed as an app' : 'Desktop and mobile app mode ready'}</span>
        </div>
      </div>
      {deferredPrompt ? (
        <button type="button" className="glass-button" onClick={install}>Install App</button>
      ) : (
        <p className="small muted">{platformHelp()}</p>
      )}
    </div>
  )
}

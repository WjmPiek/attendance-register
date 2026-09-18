import { useEffect, useState } from 'react'
import { getCoreEntities, getMe, getRoles, login } from './api/client'
import { AUTH_INVALID_EVENT, getAccessToken, setAccessToken } from './api/authSession'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import { consumeMartinsLaunch } from './martinsLaunch'

// React StrictMode can mount twice; exchange each launch token only once.
let launchRequest
function exchangeLaunch(token) {
  if (!launchRequest || launchRequest.token !== token) {
    launchRequest = { token, promise: consumeMartinsLaunch(token) }
  }
  return launchRequest.promise
}

export default function App() {
  const [launchToken] = useState(() => new URLSearchParams(window.location.search).get('martins_launch'))
  const [launching, setLaunching] = useState(Boolean(launchToken))
  const [token, setToken] = useState(() => launchToken ? null : getAccessToken())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [me, setMe] = useState(null)
  const [roles, setRoles] = useState([])
  const [entities, setEntities] = useState([])

  useEffect(() => {
    if (!launchToken) return
    let cancelled = false
    const url = new URL(window.location.href)
    url.searchParams.delete('martins_launch')
    window.history.replaceState({}, '', url)
    exchangeLaunch(launchToken).then((data) => {
      if (cancelled) return
      if (!data.access_token) throw new Error('Attendance could not verify your session. Please try opening it again from the main system.')
      setAccessToken(data.access_token)
      setToken(data.access_token)
      setError('')
    }).catch((err) => {
      if (cancelled) return
      setAccessToken(null)
      setToken(null)
      setError(err.message || 'Unable to open Attendance. Please try again from the main system.')
    }).finally(() => {
      if (!cancelled) setLaunching(false)
    })
    return () => { cancelled = true }
  }, [launchToken])

  useEffect(() => {
    const handleInvalidSession = (event) => {
      setError(event.detail?.reason || 'Your session has expired. Please sign in again.')
      setToken(null)
      setMe(null)
      setRoles([])
      setEntities([])
    }
    window.addEventListener(AUTH_INVALID_EVENT, handleInvalidSession)
    return () => window.removeEventListener(AUTH_INVALID_EVENT, handleInvalidSession)
  }, [])

  useEffect(() => {
    if (!token) return
    const load = async () => {
      try {
        const meData = await getMe()
        setMe(meData)

        // Admin metadata is optional. Employee/Manager accounts must not be
        // logged out just because roles/meta endpoints are restricted.
        try {
          const roleData = await getRoles()
          setRoles(roleData)
        } catch (_) {
          setRoles([])
        }

        try {
          const entityData = await getCoreEntities()
          setEntities(entityData.entities || [])
        } catch (_) {
          setEntities([])
        }
      } catch (err) {
        setError(err.message)
        handleLogout()
      }
    }
    load()
  }, [token])

  const handleLogin = async (loginName, password) => {
    setLoading(true)
    setError('')
    try {
      const data = await login(loginName, password)
      setAccessToken(data.access_token)
      setToken(data.access_token)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = () => {
    setAccessToken(null)
    setToken(null)
    setMe(null)
    setRoles([])
    setEntities([])
  }

  if (launching || (token && !me)) {
    return <main className="attendance-session-loading" role="status" aria-live="polite"><img src="/logo.png" alt="Martin's Funerals" /><h1>Opening Attendance Register</h1><p>Please wait while we verify your session.</p></main>
  }

  if (!token || !me) {
    return <LoginPage onLogin={handleLogin} loading={loading} error={error} />
  }

  return <DashboardPage me={me} roles={roles} entities={entities} onLogout={handleLogout} />
}

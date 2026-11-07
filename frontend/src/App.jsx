import {setStaffBranchId} from './api/branchContext'
import { useEffect, useRef, useState } from 'react'
import { usesStaffPortal } from './utils/staff-portal.mjs'
import { getCoreEntities, getMe, getRoles, login } from './api/client'
import { AUTH_INVALID_EVENT, getAccessToken, setAccessToken } from './api/authSession'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import { consumeMartinsLaunch } from './martinsLaunch'
import { embeddedParentOrigin, notifyAttendanceParent } from './embeddedAttendance'
import './embeddedAttendance.css'

// React StrictMode can mount twice; exchange each launch token only once.
let launchRequest
function exchangeLaunch(token) {
  if (!launchRequest || launchRequest.token !== token) {
    launchRequest = { token, promise: consumeMartinsLaunch(token) }
  }
  return launchRequest.promise
}

export default function App() {
  const [embedded] = useState(() => Boolean(embeddedParentOrigin()))
  const [launchToken] = useState(() => new URLSearchParams(window.location.search).get('martins_launch'))
  const [launching, setLaunching] = useState(Boolean(launchToken))
  const [token, setToken] = useState(() => launchToken ? null : getAccessToken())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [me, setMe] = useState(null)
  const [roles, setRoles] = useState([])
  const [entities, setEntities] = useState([])
  const freshLogin = useRef(false)

  useEffect(() => {
    if (!embedded) return undefined
    document.body.classList.add('attendance-is-embedded')
    let previousHeight = 0
    const publishHeight = () => {
      const height = Math.ceil(document.getElementById('root')?.getBoundingClientRect().height || 0)
      if (height !== previousHeight) {
        previousHeight = height
        notifyAttendanceParent('martins:attendance-height', {height})
      }
    }
    const observer = new ResizeObserver(publishHeight)
    observer.observe(document.getElementById('root'))
    publishHeight()
    return () => { observer.disconnect(); document.body.classList.remove('attendance-is-embedded') }
  }, [embedded])

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
      setStaffBranchId(data.active_branch_id || '')
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
        if (freshLogin.current && usesStaffPortal(meData)) {
          const url = new URL(window.location.href)
          if (!url.searchParams.has('office_qr')) {
            url.searchParams.delete('staff_portal_page'); url.searchParams.delete('staff_page'); url.searchParams.delete('tab')
            window.history.replaceState({}, '', url)
          }
        }
        freshLogin.current = false
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
      freshLogin.current = true
      setAccessToken(data.access_token)
      setToken(data.access_token)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = () => {
    freshLogin.current = false
    setAccessToken(null)
    setToken(null)
    setMe(null)
    setRoles([])
    setEntities([])
  }

  if (launching || (token && !me)) {
    if (embedded) return <section className="attendance-embedded-status" role="status" aria-live="polite">Loading attendance…</section>
    return <main className="attendance-session-loading" role="status" aria-live="polite"><img src="/logo.png" alt="Martin's Funerals" /><h1>Opening Attendance Register</h1><p>Please wait while we verify your session.</p></main>
  }

  if (!token || !me) {
    if (embedded) return <section className="attendance-embedded-status" role="alert"><p>{error || 'Your Attendance session needs to be reopened.'}</p><button type="button" onClick={() => notifyAttendanceParent('martins:attendance-retry')}>Reload Attendance</button></section>
    return <LoginPage onLogin={handleLogin} loading={loading} error={error} />
  }

  return <DashboardPage me={me} roles={roles} entities={entities} onLogout={handleLogout} embedded={embedded} />
}

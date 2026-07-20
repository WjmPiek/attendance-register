import { useEffect, useState } from 'react'
import { getCoreEntities, getMe, getRoles, login } from './api/client'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import FranchiseStaffPage from "./pages/FranchiseStaffPage";

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('token'))
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [me, setMe] = useState(null)
  const [roles, setRoles] = useState([])
  const [entities, setEntities] = useState([])

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
      localStorage.setItem('token', data.access_token)
      setToken(data.access_token)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    setToken(null)
    setMe(null)
    setRoles([])
    setEntities([])
  }

  if (!token || !me) {
    return <LoginPage onLogin={handleLogin} loading={loading} error={error} />
  }

  return <DashboardPage me={me} roles={roles} entities={entities} onLogout={handleLogout} />
}

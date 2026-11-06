import { createContext, useContext, useEffect, useState, useCallback } from 'react'
import { api, getAnonId } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const loadUser = useCallback(async () => {
    const token = localStorage.getItem('nr_token')
    if (!token) {
      setLoading(false)
      return
    }
    try {
      const data = await api.me()
      setUser(data.user)
    } catch {
      localStorage.removeItem('nr_token')
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadUser()
  }, [loadUser])

  const login = async (email, password) => {
    const data = await api.login({ email, password })
    localStorage.setItem('nr_token', data.token)
    setUser(data.user)
    return data.user
  }

  const register = async (name, email, password) => {
    const data = await api.register({ name, email, password })
    localStorage.setItem('nr_token', data.token)
    setUser(data.user)
    return data.user
  }

  // Save onboarding interests and refresh the cached user, so
  // needs_onboarding flips to false straight away.
  const saveInterests = async (interests) => {
    const data = await api.saveInterests(interests)
    setUser(data.user)
    return data.user
  }

  const logout = () => {
    localStorage.removeItem('nr_token')
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout, saveInterests, anonId: getAnonId() }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

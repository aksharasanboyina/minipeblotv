import React, { createContext, useContext, useState, useEffect } from 'react'
import axios from 'axios'

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Read any stored session up-front so the Authorization header is attached from
// the very first request (not after a post-mount effect, which let the initial
// page loads race ahead of it with no header at all).
const storedToken = localStorage.getItem('peblo_token')

export const api = axios.create({
  baseURL: API_URL,
})

function applyAuth(token: string | null) {
  if (token) {
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`
  } else {
    delete api.defaults.headers.common['Authorization']
  }
}

if (storedToken) applyAuth(storedToken)

// A stale/expired/invalid token currently manifests as endless 401s with no way
// to recover except a manual log-out. On any 401 from a protected route, drop the
// stored session and bounce to the login screen instead.
let unauthorizedHandler: (() => void) | null = null
export function setUnauthorizedHandler(fn: (() => void) | null) {
  unauthorizedHandler = fn
}

api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error?.response?.status
    const url: string = error?.config?.url || ''
    if (status === 401 && !url.includes('/auth/token')) {
      localStorage.removeItem('peblo_token')
      localStorage.removeItem('peblo_role')
      applyAuth(null)
      unauthorizedHandler?.()
    }
    return Promise.reject(error)
  }
)

export interface AuthContextType {
  token: string | null
  role: string | null
  login: (user_id: string, role: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType>({
  token: null,
  role: null,
  login: async () => {},
  logout: () => {},
})

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(storedToken)
  const [role, setRole] = useState<string | null>(localStorage.getItem('peblo_role'))

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setToken(null)
      setRole(null)
    })
    return () => setUnauthorizedHandler(null)
  }, [])

  useEffect(() => {
    applyAuth(token)
  }, [token])

  const login = async (user_id: string, role: string) => {
    const resp = await axios.post(`${API_URL}/auth/token`, { user_id, role })
    const { access_token } = resp.data
    localStorage.setItem('peblo_token', access_token)
    localStorage.setItem('peblo_role', role)
    applyAuth(access_token)
    setToken(access_token)
    setRole(role)
  }

  const logout = () => {
    localStorage.removeItem('peblo_token')
    localStorage.removeItem('peblo_role')
    applyAuth(null)
    setToken(null)
    setRole(null)
  }

  return (
    <AuthContext.Provider value={{ token, role, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)

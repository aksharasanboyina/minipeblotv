import React, { createContext, useContext, useState } from 'react'
import axios from 'axios'
import { API_URL, clearViewerSession, getStoredToken, setViewerSession } from '../api'

export interface AuthContextType {
  token: string | null
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType>({
  token: null,
  login: async () => {},
  logout: () => {},
})

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(getStoredToken())

  const login = async (email: string, password: string) => {
    const resp = await axios.post(`${API_URL}/auth/viewer/token`, { email, password })
    const { access_token, role } = resp.data
    setViewerSession(access_token, role)
    setToken(access_token)
  }

  const logout = () => {
    clearViewerSession()
    setToken(null)
  }

  return (
    <AuthContext.Provider value={{ token, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)

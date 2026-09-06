import axios from 'axios'

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const TOKEN_KEY = 'peblo_viewer_token'

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

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

// Attach any stored session up-front so the first request after a refresh is authed.
applyAuth(getStoredToken())

// A dead/expired viewer session must bounce to the login screen, not leave the
// app silently broken on endless 401s.
api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const status = error?.response?.status
    const url: string = error?.config?.url || ''
    if (status === 401 && !url.includes('/auth/viewer/token')) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem('peblo_viewer_role')
      delete api.defaults.headers.common['Authorization']
      if (window.location.pathname !== '/login') {
        window.location.assign('/login')
      }
    }
    return Promise.reject(error)
  }
)

export function setViewerSession(token: string, role: string) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem('peblo_viewer_role', role)
  applyAuth(token)
}

export function clearViewerSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem('peblo_viewer_role')
  applyAuth(null)
}

export function resolveUrl(path: string | null): string | null {
  if (!path) return null
  if (path.startsWith('http')) return path
  return `${API_URL}${path}`
}

// <video> elements cannot send an Authorization header, so clips stream through
// the viewer-gated endpoint with the token as a query param (?token=...).
export function videoStreamUrl(episodeId: string): string | null {
  const token = getStoredToken()
  if (!token) return null
  return `${API_URL}/catalog/video/${episodeId}?token=${encodeURIComponent(token)}`
}

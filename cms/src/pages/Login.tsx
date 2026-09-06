import { useState } from 'react'
import { useAuth } from '../context/AuthContext'

const DEMO_USERS = [
  { user_id: 'admin@peblo.tv', role: 'admin', label: 'Admin (can publish)' },
  { user_id: 'editor@peblo.tv', role: 'editor', label: 'Editor (no publish)' },
]

export default function Login() {
  const { login } = useAuth()
  const [userId, setUserId] = useState(DEMO_USERS[0].user_id)
  const [role, setRole] = useState('admin')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(userId, role)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      <div className="card login-card">
        <h1>Peblo TV CMS</h1>
        <p className="muted">Internal content management system</p>

        <form onSubmit={handleSubmit}>
          <label className="field">
            <span>User</span>
            <select
              value={userId}
              onChange={(e) => {
                const u = DEMO_USERS.find(x => x.user_id === e.target.value)
                setUserId(e.target.value)
                if (u) setRole(u.role)
              }}
            >
              {DEMO_USERS.map(u => (
                <option key={u.user_id} value={u.user_id}>{u.label}</option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Role</span>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="admin">Admin</option>
              <option value="editor">Editor</option>
            </select>
          </label>

          {error && <div className="alert alert-error">{error}</div>}

          <button type="submit" className="btn btn-primary btn-block" disabled={loading}>
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="hint muted">
          Demo users only. In production this would use SSO / OAuth.
        </p>
      </div>
    </div>
  )
}

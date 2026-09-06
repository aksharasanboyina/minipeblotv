import { useState } from 'react'
import { useAuth } from '../context/AuthContext'

const DEMO_EMAIL = 'kids@peblo.tv'
const DEMO_PASSWORD = 'peblo123'

export default function Login() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email.trim(), password)
    } catch (err: any) {
      const detail = err?.response?.data?.detail
      setError(typeof detail === 'string' ? detail : 'We can\'t find an account with that email and password.')
    } finally {
      setLoading(false)
    }
  }

  const fillDemo = () => {
    setEmail(DEMO_EMAIL)
    setPassword(DEMO_PASSWORD)
  }

  return (
    <div className="login-bg">
      <div className="login-brand">PEBLO&nbsp;<span className="brand-sub">TV</span></div>

      <form className="login-card" onSubmit={handleSubmit}>
        <h1>Sign In</h1>

        <label className="login-field">
          <input
            type="email"
            placeholder="Email or phone number"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />
        </label>

        <label className="login-field">
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>

        {error && <div className="login-error">{error}</div>}

        <button type="submit" className="login-btn" disabled={loading}>
          {loading ? 'Signing in…' : 'Sign In'}
        </button>

        <div className="login-help">
          <span>New to Peblo TV? </span>
          <button type="button" className="login-link" onClick={fillDemo}>
            Try the demo account
          </button>
          <p className="login-demo">
            Demo — {DEMO_EMAIL} / {DEMO_PASSWORD}
          </p>
        </div>

        <p className="login-footnote">
          This is a demo sign-in. In production it would use real child-profile
          identity flows.
        </p>
      </form>
    </div>
  )
}

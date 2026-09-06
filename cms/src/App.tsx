import { Routes, Route, NavLink, Navigate } from 'react-router-dom'
import ShowsList from './pages/ShowsList'
import ShowEdit from './pages/ShowEdit'
import PublishPage from './pages/PublishPage'
import Login from './pages/Login'
import { AuthProvider, useAuth } from './context/AuthContext'

function Shell() {
  const { token, role, logout } = useAuth()

  if (!token) {
    return <Login />
  }

  return (
    <div className="app-shell">
      <nav className="topnav">
        <div className="brand">Peblo TV · CMS</div>
        <div className="nav-links">
          <NavLink to="/shows" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            Shows
          </NavLink>
          <NavLink to="/publish" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            Publish
          </NavLink>
        </div>
        <div className="nav-right">
          <span className="role-badge">{role === 'admin' ? '👑 Admin' : '✏️ Editor'}</span>
          <button className="btn btn-ghost" onClick={logout}>Log out</button>
        </div>
      </nav>

      <div className="content">
        <Routes>
          <Route path="/shows" element={<ShowsList />} />
          <Route path="/shows/:showId" element={<ShowEdit />} />
          <Route path="/publish" element={<PublishPage />} />
          <Route path="/" element={<Navigate to="/shows" replace />} />
          <Route path="*" element={<Navigate to="/shows" replace />} />
        </Routes>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  )
}

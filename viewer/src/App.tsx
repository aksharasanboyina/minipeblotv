import { Routes, Route, NavLink, Link } from 'react-router-dom'
import Home from './pages/Home'
import Search from './pages/Search'
import ShowDetail from './pages/ShowDetail'
import Watch from './pages/Watch'
import Login from './pages/Login'
import { useAuth } from './context/AuthContext'

function Shell() {
  const { token, logout } = useAuth()

  if (!token) {
    return <Login />
  }

  return (
    <div className="viewer">
      <nav className="viewer-nav">
        <Link to="/" className="viewer-brand">PEBLO&nbsp;TV</Link>
        <NavLink to="/" className={({ isActive }) => isActive ? 'viewer-link active' : 'viewer-link'} end>
          Home
        </NavLink>
        <NavLink to="/search" className={({ isActive }) => isActive ? 'viewer-link active' : 'viewer-link'}>
          Search
        </NavLink>

        <div className="nav-right">
          <span className="profile-chip">👦 Kids</span>
          <button className="logout-btn" onClick={logout}>Sign out</button>
        </div>
      </nav>

      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/search" element={<Search />} />
        <Route path="/show/:slug" element={<ShowDetail />} />
        <Route path="/watch/:slug/:episodeId" element={<Watch />} />
        <Route path="*" element={<Home />} />
      </Routes>
    </div>
  )
}

export default function App() {
  return <Shell />
}

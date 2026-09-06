import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../context/AuthContext'
import { useAuth } from '../context/AuthContext'

const SECTIONS = ['featured', 'series', 'minisodes', 'songs']
const STATUSES = ['draft', 'published']

export default function ShowsList() {
  const [search, setSearch] = useState('')
  const [section, setSection] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const { role } = useAuth()

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['shows', search, section, status, page],
    queryFn: async () => {
      const params: any = { page, page_size: 20 }
      if (search) params.search = search
      if (section) params.section = section
      if (status) params.status = status
      const resp = await api.get('/admin/shows', { params })
      return resp.data
    },
  })

  return (
    <div className="page">
      <div className="page-header">
        <h1>Shows</h1>
        {role === 'admin' && (
          <Link to="/publish" className="btn btn-primary">Go to Publish</Link>
        )}
      </div>

      <div className="filters">
        <input
          type="text"
          placeholder="Search by title…"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          className="input"
        />
        <select value={section} onChange={(e) => { setSection(e.target.value); setPage(1) }} className="input">
          <option value="">All sections</option>
          {SECTIONS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className="input">
          <option value="">All statuses</option>
          {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>

      {isLoading && <div className="alert">Loading shows…</div>}

      {isError && (
        <div className="alert alert-error">
          Could not load shows. {error instanceof Error ? error.message : ''}
        </div>
      )}

      {data && data.items.length === 0 && (
        <div className="empty-state">
          <p>No shows match your filters.</p>
          <p className="muted">Try clearing the search or filters.</p>
        </div>
      )}

      {data && data.items.length > 0 && (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Section</th>
                <th>Categories</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((show: any) => (
                <tr key={show.id}>
                  <td><strong>{show.title}</strong></td>
                  <td><span className="badge">{show.section || '—'}</span></td>
                  <td className="muted">{show.categories.join(', ')}</td>
                  <td>
                    <span className={`status-dot ${show.status}`}>{show.status}</span>
                  </td>
                  <td>
                    <Link to={`/shows/${show.id}`} className="btn btn-small">Edit</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="pagination">
            <button
              className="btn btn-small"
              disabled={page <= 1}
              onClick={() => setPage(p => p - 1)}
            >
              ← Prev
            </button>
            <span>Page {data.page} of {data.total_pages} · {data.total} shows</span>
            <button
              className="btn btn-small"
              disabled={page >= data.total_pages}
              onClick={() => setPage(p => p + 1)}
            >
              Next →
            </button>
          </div>
        </>
      )}
    </div>
  )
}

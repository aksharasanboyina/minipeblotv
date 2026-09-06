import { useState, useEffect, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../context/AuthContext'
import ArtworkUpload from '../components/ArtworkUpload'

// Compact per-episode thumbnail uploader. The publish validator requires every
// published episode to have a thumbnail, and episode artwork is only reachable
// through this slot (the API accepts entity_type=episode).
function EpisodeThumbUpload({ episodeId, episodeLabel }: { episodeId: string; episodeLabel: string }) {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [state, setState] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle')
  const [message, setMessage] = useState<string[]>([])

  const upload = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    setState('uploading')
    setMessage([])
    try {
      await api.post(`/admin/artwork/episode/${episodeId}`, formData, {
        params: { artwork_type: 'thumbnail' },
      })
      setState('done')
      queryClient.invalidateQueries({ queryKey: ['artworks'] })
    } catch (err: any) {
      setState('error')
      const detail = err?.response?.data?.detail
      const errors = detail && typeof detail === 'object' && detail.errors ? detail.errors : [String(detail || err?.message || 'Upload failed')]
      setMessage(errors)
    }
  }

  return (
    <div className="ep-thumb-upload">
      <button
        type="button"
        className="btn btn-small"
        onClick={() => inputRef.current?.click()}
        disabled={state === 'uploading'}
        title={`Upload a 640×360 JPEG/PNG thumbnail for ${episodeLabel}`}
      >
        {state === 'uploading' ? 'Uploading…' : state === 'done' ? 'Uploaded ✓' : '📤 Thumb'}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) upload(file)
          e.target.value = ''
        }}
      />
      {state === 'error' && message.length > 0 && (
        <div className="muted thumb-error">{message.join(' · ')}</div>
      )}
    </div>
  )
}

function formatBytes(n: number | null | undefined): string {
  if (!n && n !== 0) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

// Per-episode real-video uploader. Videos are stored per content group, so an
// upload for any language variant replaces the episode's video (including the
// generated placeholder clip) and the viewer streams it after the next publish.
function EpisodeVideoUpload({ episodeId, episodeLabel }: { episodeId: string; episodeLabel: string }) {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [state, setState] = useState<'idle' | 'uploading' | 'done' | 'error'>('idle')
  const [message, setMessage] = useState<string[]>([])

  const { data: video } = useQuery({
    queryKey: ['episode-video', episodeId],
    queryFn: async () => (await api.get(`/admin/videos/${episodeId}`)).data,
  })

  const upload = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    setState('uploading')
    setMessage([])
    try {
      const resp = await api.post(`/admin/videos/${episodeId}`, formData)
      setState('done')
      setMessage([`Uploaded ${resp.data.ext?.toUpperCase?.() || 'video'}`])
      queryClient.invalidateQueries({ queryKey: ['episode-video', episodeId] })
    } catch (err: any) {
      setState('error')
      const detail = err?.response?.data?.detail
      const errors = detail && typeof detail === 'object' && detail.errors ? detail.errors : [String(detail || err?.message || 'Upload failed')]
      setMessage(errors)
    }
  }

  const remove = async () => {
    setState('uploading')
    try {
      await api.delete(`/admin/videos/${episodeId}`)
      setState('done')
      setMessage(['Removed'])
      queryClient.invalidateQueries({ queryKey: ['episode-video', episodeId] })
    } catch (err: any) {
      setState('error')
      const detail = err?.response?.data?.detail
      setMessage([String(typeof detail === 'string' ? detail : detail?.message || err?.message || 'Delete failed')])
    }
  }

  const uploaded = video?.uploaded

  return (
    <div className="ep-video-upload">
      <button
        type="button"
        className="btn btn-small"
        onClick={() => inputRef.current?.click()}
        disabled={state === 'uploading'}
        title={`Upload an MP4/WebM for ${episodeLabel} (replaces the current video)`}
      >
        {state === 'uploading' ? 'Working…' : uploaded ? '📹 Replace' : '📹 Upload'}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="video/mp4,video/webm"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) upload(file)
          e.target.value = ''
        }}
      />
      {uploaded && video?.file_size_bytes !== null && video?.file_size_bytes !== undefined && (
        <button type="button" className="btn btn-small btn-danger" onClick={remove} disabled={state === 'uploading'}>
          ✕
        </button>
      )}
      <div className="muted ep-video-meta">
        {uploaded
          ? `${(video.ext || '').toUpperCase()} · ${formatBytes(video.file_size_bytes)}`
          : 'No video yet'}
      </div>
      {(state === 'done' || state === 'error') && message.length > 0 && (
        <div className="muted thumb-error">{message.join(' · ')}</div>
      )}
    </div>
  )
}

const SECTIONS = ['featured', 'series', 'minisodes', 'songs']
const CATEGORIES = ['adventure', 'folk', 'friendship', 'india', 'language', 'learning',
  'maths', 'music', 'nature', 'reading', 'science', 'singalong', 'stories', 'travel', 'values']

export default function ShowEdit() {
  const { showId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: show, isLoading, isError } = useQuery({
    queryKey: ['show', showId],
    queryFn: async () => (await api.get(`/admin/shows/${showId}`)).data,
  })

  const { data: seasons } = useQuery({
    queryKey: ['seasons', showId],
    queryFn: async () => (await api.get(`/admin/shows/${showId}/seasons`)).data,
  })

  const { data: artworks } = useQuery({
    queryKey: ['artworks', 'show', showId],
    queryFn: async () => (await api.get(`/admin/artwork/show/${showId}`)).data,
  })

  const [form, setForm] = useState<any>(null)
  useEffect(() => {
    if (show) setForm({ ...show, categories: show.categories || [] })
  }, [show])

  const updateMutation = useMutation({
    mutationFn: async (data: any) => {
      const resp = await api.put(`/admin/shows/${showId}`, data)
      return resp.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['show', showId] })
    },
  })

  const toggleCategory = (cat: string) => {
    setForm((f: any) => {
      const cats = f.categories.includes(cat)
        ? f.categories.filter((c: string) => c !== cat)
        : [...f.categories, cat]
      return { ...f, categories: cats }
    })
  }

  if (isLoading) return <div className="alert">Loading show…</div>
  if (isError || !show) return <div className="alert alert-error">Show not found.</div>
  if (!form) return null

  return (
    <div className="page">
      <div className="page-header">
        <h1>{show.title}</h1>
        <button className="btn" onClick={() => navigate('/shows')}>← Back</button>
      </div>

      <div className="card">
        <h2>Show details</h2>
        <div className="form-grid">
          <label className="field">
            <span>Title</span>
            <input
              className="input"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Slug</span>
            <input
              className="input"
              value={form.slug}
              onChange={(e) => setForm({ ...form, slug: e.target.value })}
            />
          </label>
          <label className="field">
            <span>Section</span>
            <select
              className="input"
              value={form.section || ''}
              onChange={(e) => setForm({ ...form, section: e.target.value || null })}
            >
              <option value="">— No section —</option>
              {SECTIONS.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          <label className="field">
            <span>Status</span>
            <select
              className="input"
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
            >
              <option value="draft">Draft</option>
              <option value="published">Published</option>
            </select>
          </label>
          <label className="field field-full">
            <span>Synopsis</span>
            <textarea
              className="input"
              rows={4}
              value={form.synopsis || ''}
              onChange={(e) => setForm({ ...form, synopsis: e.target.value })}
            />
          </label>
        </div>

        <div className="field">
          <span className="field-label">Categories</span>
          <div className="chips">
            {CATEGORIES.map(cat => (
              <button
                key={cat}
                type="button"
                className={`chip ${form.categories.includes(cat) ? 'chip-active' : ''}`}
                onClick={() => toggleCategory(cat)}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        <div className="form-actions">
          <button
            className="btn btn-primary"
            onClick={() => updateMutation.mutate(form)}
            disabled={updateMutation.isPending}
          >
            {updateMutation.isPending ? 'Saving…' : 'Save changes'}
          </button>
          {updateMutation.isError && (
            <span className="alert alert-error inline">
              Save failed: {JSON.stringify((updateMutation.error as any)?.response?.data?.detail || updateMutation.error?.message)}
            </span>
          )}
          {updateMutation.isSuccess && <span className="alert alert-success inline">Saved ✓</span>}
        </div>
      </div>

      <div className="card">
        <h2>Artwork</h2>
        <p className="muted">Upload the three required artwork sizes. Each must meet its specifications or it will be rejected.</p>
        <div className="artwork-slots">
          <ArtworkUpload entityType="show" entityId={showId!} artworkType="poster" />
          <ArtworkUpload entityType="show" entityId={showId!} artworkType="banner" />
          <ArtworkUpload entityType="show" entityId={showId!} artworkType="thumbnail" />
        </div>

        {artworks && artworks.length > 0 && (
          <div className="artwork-list">
            <h3>Uploaded artwork</h3>
            {artworks.map((a: any) => (
              <div key={a.id} className="artwork-item">
                <img src={`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}${a.file_path}`} alt={a.artwork_type} width={80} />
                <span>{a.artwork_type} · {a.width}×{a.height} · {Math.round(a.file_size_bytes / 1024)} KB</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <h2>Seasons & Episodes</h2>
        <p className="muted">
          Season 0 is reserved for trailers and won't show as a normal season in the viewer.
        </p>
        {seasons && seasons.length === 0 && (
          <div className="empty-state">
            <p>No seasons yet.</p>
          </div>
        )}
        {seasons && seasons.map((season: any) => (
          <SeasonBlock key={season.id} season={season} />
        ))}
      </div>
    </div>
  )
}

function SeasonBlock({ season }: { season: { id: string; season_number: number } }) {
  const { data: episodes } = useQuery({
    queryKey: ['episodes', season.id],
    queryFn: async () => (await api.get(`/admin/seasons/${season.id}/episodes`, { params: { page_size: 100 } })).data,
  })

  const seasonLabel = season.season_number === 0
    ? `Season 0 (Trailers)`
    : `Season ${season.season_number}`

  return (
    <div className="season-block">
      <h3>{seasonLabel}</h3>
      {episodes && episodes.items.length > 0 ? (
        <table className="table table-compact">
          <thead>
            <tr>
              <th>Ep #</th>
              <th>Title</th>
              <th>Lang</th>
              <th>Duration</th>
              <th>Content group</th>
              <th>Status</th>
              <th>Thumbnail</th>
              <th>Video</th>
            </tr>
          </thead>
          <tbody>
            {episodes.items.map((ep: any) => (
              <tr key={ep.id}>
                <td>{ep.episode_number}</td>
                <td>{ep.title}</td>
                <td>{ep.language}</td>
                <td>{ep.duration_seconds ? `${Math.round(ep.duration_seconds / 60)}m` : '—'}</td>
                <td className="muted">{ep.content_group}</td>
                <td><span className={`status-dot ${ep.status}`}>{ep.status}</span></td>
                <td>
                  {ep.status === 'published' ? (
                    <EpisodeThumbUpload episodeId={ep.id} episodeLabel={`${ep.title} (${ep.language})`} />
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td>
                  <EpisodeVideoUpload episodeId={ep.id} episodeLabel={`${ep.title} (${ep.language})`} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">No episodes in this season.</p>
      )}
    </div>
  )
}

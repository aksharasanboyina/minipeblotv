import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, resolveUrl } from '../api'

function LazyImage({ src, alt, className }: { src: string | null; alt: string; className?: string }) {
  if (!src) return <div className={`img-placeholder ${className || ''}`}>No artwork</div>
  return (
    <img
      src={src}
      alt={alt}
      className={className}
      loading="lazy"
      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
    />
  )
}

export default function ShowDetail() {
  const { slug } = useParams()
  const [selectedSeason, setSelectedSeason] = useState<number | null>(null)

  const { data: show, isLoading, isError } = useQuery({
    queryKey: ['show', slug],
    queryFn: async () => (await api.get(`/catalog/shows/${slug}`)).data,
  })

  if (isLoading) return <div className="viewer-content"><div className="skeleton detail-skeleton" /></div>
  if (isError || !show) {
    return (
      <div className="viewer-content empty">
        <h2>Show not found</h2>
        <p>This show isn't in the published catalogue.</p>
        <Link to="/" className="viewer-btn">Back to home</Link>
      </div>
    )
  }

  const seasons = show.seasons || []
  const seasonNumbers: number[] = seasons.filter((s: any) => s.season_number > 0).map((s: any) => s.season_number)
  const activeSeason = selectedSeason ?? (seasonNumbers.length > 0 ? seasonNumbers[0] : null)
  const activeSeasonData = seasons.find((s: any) => s.season_number === activeSeason)

  return (
    <div className="detail-page">
      <div className="detail-hero" style={{ backgroundImage: show.banner_url ? `url(${resolveUrl(show.banner_url)})` : 'none' }}>
        <div className="detail-overlay">
          <Link to="/" className="back-link">← Back</Link>
          <h1>{show.title}</h1>
          <p className="detail-synopsis">{show.synopsis}</p>
          <div className="detail-meta">
            <span className="badge">{show.section}</span>
            {show.categories.map((c: string) => (
              <span key={c} className="badge badge-ghost">{c}</span>
            ))}
          </div>
        </div>
      </div>

      <div className="viewer-content">
        {show.has_trailer && (
          <div className="trailer-note">
            🎬 This show has a trailer available.
          </div>
        )}

        {seasonNumbers.length > 0 ? (
          <>
            <div className="season-tabs">
              {seasonNumbers.map(num => (
                <button
                  key={num}
                  className={`season-tab ${activeSeason === num ? 'active' : ''}`}
                  onClick={() => setSelectedSeason(num)}
                >
                  Season {num}
                </button>
              ))}
            </div>

            {activeSeasonData && (
              <div className="episode-list">
                {activeSeasonData.episodes.map((ep: any) => (
                  <div key={ep.episode_id} className="episode-item">
                    <div className="episode-thumb">
                      <LazyImage src={resolveUrl(ep.thumbnail_url)} alt={ep.title} />
                      <span className="ep-number">E{ep.episode_number}</span>
                    </div>
                    <div className="episode-info">
                      <h4>{ep.title}</h4>
                      <p className="muted">
                        {ep.duration_seconds ? `${Math.round(ep.duration_seconds / 60)} min` : ''}
                      </p>
                      {ep.languages && ep.languages.length > 0 && (
                        <div className="lang-options">
                          {ep.languages.map((l: string) => (
                            <span key={l} className="lang-pill">{l === 'en' ? 'English' : 'Hindi'}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="episode-actions">
                      {ep.has_video && ep.video_url ? (
                        <Link
                          to={`/watch/${show.slug}/${ep.episode_id}`}
                          className="viewer-btn play-btn"
                        >
                          ▶ Play
                        </Link>
                      ) : (
                        <span className="muted coming-soon">Video coming soon</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : (
          <div className="empty">
            <h3>No episodes published yet</h3>
            <p>This show has no published episodes in the catalogue.</p>
          </div>
        )}
      </div>
    </div>
  )
}

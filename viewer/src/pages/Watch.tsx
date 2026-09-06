import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, resolveUrl, videoStreamUrl } from '../api'

export default function Watch() {
  const { slug, episodeId } = useParams()
  const { data: show, isLoading } = useQuery({
    queryKey: ['show', slug],
    queryFn: async () => (await api.get(`/catalog/shows/${slug}`)).data,
  })

  const episode = show
    ? (show.seasons || [])
        .flatMap((s: any) => s.episodes || [])
        .find((ep: any) => String(ep.episode_id) === episodeId)
    : null

  const seasonNumber = episode
    ? (show.seasons || []).find((s: any) => (s.episodes || []).some((ep: any) => String(ep.episode_id) === episodeId))?.season_number
    : null

  const src = episode ? videoStreamUrl(String(episode.episode_id)) : null

  if (isLoading) {
    return <div className="watch-page"><div className="skeleton watch-skeleton" /></div>
  }

  if (!show || !episode) {
    return (
      <div className="watch-page">
        <div className="watch-topbar">
          <Link to="/" className="watch-back">← Back to browse</Link>
        </div>
        <div className="watch-empty">
          <h2>Title not found</h2>
          <p>This title isn't in the catalogue.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="watch-page">
      <div className="watch-topbar">
        <Link to={`/show/${show.slug}`} className="watch-back">← {show.title}</Link>
        <span className="watch-brand">PEBLO TV</span>
      </div>

      <div className="video-frame">
        {src ? (
          <video
            key={episode.episode_id}
            controls
            autoPlay
            playsInline
            poster={resolveUrl(episode.thumbnail_url) || undefined}
            src={src}
            className="video-player"
          />
        ) : (
          <div className="watch-empty">
            <h2>Video coming soon</h2>
            <p>
              A playable clip hasn't been generated for this episode yet.
              Publish a catalogue on a server with ffmpeg available and it will
              appear here.
            </p>
          </div>
        )}
      </div>

      {episode && (
        <div className="watch-info">
          <h1>
            {show.title} — {episode.title}
          </h1>
          <p className="muted">
            {seasonNumber ? `Season ${seasonNumber} · ` : ''}
            Episode {episode.episode_number}
            {episode.duration_seconds ? ` · ${Math.round(episode.duration_seconds / 60)} min` : ''}
            {episode.languages?.length ? ` · ${episode.languages.map((l: string) => (l === 'en' ? 'English' : 'Hindi')).join(' / ')}` : ''}
          </p>
          <p className="watch-synopsis">{episode.synopsis || show.synopsis}</p>
        </div>
      )}
    </div>
  )
}

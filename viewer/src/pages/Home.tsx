import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, resolveUrl } from '../api'

function LazyImage({ src, alt, className }: { src: string | null; alt: string; className?: string }) {
  if (!src) {
    return <div className={`img-placeholder ${className || ''}`}>No artwork</div>
  }
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

export default function Home() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['catalogue'],
    queryFn: async () => (await api.get('/catalog')).data,
  })

  if (isLoading) {
    return (
      <div className="viewer-content">
        <div className="skeleton hero-skeleton" />
        <div className="skeleton-row">
          {[1, 2, 3, 4, 5].map(i => <div key={i} className="skeleton card-skeleton" />)}
        </div>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="viewer-content empty">
        <h2>No catalogue yet</h2>
        <p>This viewer reads a published catalogue. Ask an admin to publish before browsing.</p>
      </div>
    )
  }

  const sections = data.sections || []
  const hero = sections[0]?.shows?.[0]

  return (
    <div>
      {hero && (
        <div className="hero" style={{ backgroundImage: hero.banner_url ? `url(${resolveUrl(hero.banner_url)})` : 'none' }}>
          <div className="hero-overlay">
            <h1>{hero.title}</h1>
            <p>{hero.synopsis}</p>
            <Link to={`/show/${hero.slug}`} className="viewer-btn">Watch now</Link>
          </div>
        </div>
      )}

      <div className="viewer-content">
        {sections.map((section: any) => (
          <section key={section.section} className="row-section">
            <h2 className="row-title">{section.section.charAt(0).toUpperCase() + section.section.slice(1)}</h2>
            <div className="poster-row">
              {section.shows.map((show: any) => (
                <Link key={show.show_id} to={`/show/${show.slug}`} className="poster-card">
                  <LazyImage src={resolveUrl(show.poster_url)} alt={show.title} className="poster-img" />
                  <div className="poster-title">{show.title}</div>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}

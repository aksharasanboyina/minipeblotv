import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { api, resolveUrl } from '../api'

const ALL_CATEGORIES = ['adventure', 'folk', 'friendship', 'india', 'language', 'learning',
  'maths', 'music', 'nature', 'reading', 'science', 'singalong', 'stories', 'travel', 'values']
const ALL_LANGUAGES = ['en', 'hi']

export default function Search() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [q, setQ] = useState(searchParams.get('q') || '')
  const [category, setCategory] = useState(searchParams.get('category') || '')
  const [language, setLanguage] = useState(searchParams.get('language') || '')

  const queryClient = useQueryClient()

  const { data, isLoading, isError } = useQuery({
    queryKey: ['search', q, category, language],
    queryFn: async () => {
      const params: any = {}
      if (q) params.q = q
      if (category) params.category = category
      if (language) params.language = language
      const resp = await api.get('/catalog/search', { params })
      return resp.data
    },
  })

  const applyFilters = () => {
    const params: any = {}
    if (q) params.q = q
    if (category) params.category = category
    if (language) params.language = language
    setSearchParams(params)
    queryClient.invalidateQueries({ queryKey: ['search'] })
  }

  const hasFilters = q || category || language

  return (
    <div className="viewer-content">
      <h1 className="page-title">Search</h1>

      <div className="search-bar">
        <input
          type="text"
          placeholder="Search shows, episodes, categories…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && applyFilters()}
          className="search-input"
        />
        <button onClick={applyFilters} className="viewer-btn">Search</button>
      </div>

      <div className="filter-row">
        <select value={category} onChange={(e) => { setCategory(e.target.value); applyFilters() }} className="search-select">
          <option value="">All categories</option>
          {ALL_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>

        <select value={language} onChange={(e) => { setLanguage(e.target.value); applyFilters() }} className="search-select">
          <option value="">All languages</option>
          {ALL_LANGUAGES.map(l => <option key={l} value={l}>{l === 'en' ? 'English' : 'Hindi'}</option>)}
        </select>
      </div>

      {!hasFilters && (
        <div className="prompt">
          <p>Type something or pick a filter to find shows and episodes.</p>
        </div>
      )}

      {isLoading && hasFilters && <div className="loading">Searching…</div>}
      {isError && hasFilters && <div className="loading">Search failed. Is the catalogue published?</div>}

      {hasFilters && data && data.total === 0 && (
        <div className="empty">
          <h3>Nothing found</h3>
          <p>Try a different search term, category, or language.</p>
        </div>
      )}

      {data && data.total > 0 && (
        <div>
          <p className="result-count">{data.total} result{data.total !== 1 ? 's' : ''}</p>
          {data.results.map((show: any) => (
            <div key={show.show_id} className="search-result">
              <Link to={`/show/${show.slug}`} className="search-result-link">
                <div className="search-thumb">
                  {show.poster_url
                    ? <img src={resolveUrl(show.poster_url)!} alt={show.title} />
                    : <div className="img-placeholder">No artwork</div>}
                </div>
                <div className="search-info">
                  <h3>{show.title}</h3>
                  <p className="muted">{show.categories.join(' · ')} · {show.section}</p>
                  {(show.seasons || []).map((season: any) => (
                    <div key={season.season_number}>
                      {season.episodes.length > 0 && (
                        <p className="ep-match">
                          S{season.season_number} E{season.episodes[0].episode_number}: {season.episodes[0].title}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

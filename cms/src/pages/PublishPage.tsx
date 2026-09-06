import { useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../context/AuthContext'
import { useAuth } from '../context/AuthContext'

export default function PublishPage() {
  const { role } = useAuth()
  const queryClient = useQueryClient()

  const { data: report, isLoading, refetch } = useQuery({
    queryKey: ['validation'],
    queryFn: async () => (await api.get('/admin/validation-report')).data,
  })

  const { data: runs } = useQuery({
    queryKey: ['publish-runs'],
    queryFn: async () => (await api.get('/admin/publish-runs')).data,
  })

  const publishMutation = useMutation({
    mutationFn: async () => {
      const resp = await api.post('/admin/catalog/publish')
      return resp.data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['validation'] })
      queryClient.invalidateQueries({ queryKey: ['publish-runs'] })
    },
  })

  useEffect(() => {
    const interval = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: ['validation'] })
      queryClient.invalidateQueries({ queryKey: ['publish-runs'] })
    }, 15000)
    return () => clearInterval(interval)
  }, [queryClient])

  const canPublish = report?.can_publish

  return (
    <div className="page">
      <div className="page-header">
        <h1>Publish</h1>
        <button className="btn" onClick={() => refetch()}>Refresh</button>
      </div>

      {isLoading && <div className="alert">Checking validation…</div>}

      {report && (
        <div className="card">
          <h2>Validation report</h2>

          {canPublish ? (
            <div className="alert alert-success">
              ✓ All checks passed. You can publish the catalogue.
            </div>
          ) : (
            <div className="alert alert-error">
              ✗ {report.blocking.length} blocking issue{report.blocking.length !== 1 ? 's' : ''} must be fixed before publishing.
            </div>
          )}

          {report.blocking.length > 0 && (
            <div className="issues">
              <h3>Blocking issues ({report.blocking.length})</h3>
              {report.blocking.map((item: any, i: number) => (
                <div key={i} className="issue-item">
                  <strong>{item.entity_name}</strong>
                  <ul>
                    {item.issues.map((issue: string, j: number) => (
                      <li key={j}>{issue}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}

          {report.warnings.length > 0 && (
            <div className="issues warnings">
              <h3>Warnings ({report.warnings.length})</h3>
              {report.warnings.map((item: any, i: number) => (
                <div key={i} className="issue-item">
                  <strong>{item.entity_name}</strong>
                  <ul>
                    {item.issues.map((issue: string, j: number) => (
                      <li key={j}>{issue}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="card">
        <h2>Publish catalogue</h2>
        <p className="muted">
          {role === 'admin'
            ? 'Publishing rebuilds catalogue.json and swaps it atomically. Readers never see a half-written file.'
            : 'Only admins can publish. Ask an admin to trigger this.'}
        </p>

        <button
          className="btn btn-publish"
          disabled={!canPublish || role !== 'admin' || publishMutation.isPending}
          onClick={() => publishMutation.mutate()}
        >
          {publishMutation.isPending
            ? 'Publishing…'
            : canPublish && role === 'admin'
            ? '🚀 Publish catalogue'
            : role !== 'admin'
            ? '🔒 Admin only'
            : '🔒 Fix issues to publish'}
        </button>

        {role !== 'admin' && (
          <p className="hint muted">Your current role is editor. You cannot publish.</p>
        )}

        {!canPublish && role === 'admin' && (
          <p className="hint">Fix the blocking issues above first.</p>
        )}

        {publishMutation.isError && (
          <div className="alert alert-error">
            Publish failed: {JSON.stringify((publishMutation.error as any)?.response?.data?.detail || 'Unknown error')}
          </div>
        )}

        {publishMutation.isSuccess && (
          <div className="alert alert-success">
            ✓ Published successfully! {publishMutation.data.shows_published} shows, {publishMutation.data.episodes_published} episodes.
          </div>
        )}
      </div>

      <div className="card">
        <h2>Run history</h2>
        {runs && runs.length === 0 && <p className="muted">No publish runs yet.</p>}
        {runs && runs.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>When</th>
                <th>By</th>
                <th>Outcome</th>
                <th>Shows</th>
                <th>Episodes</th>
                <th>Current</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run: any) => (
                <tr key={run.id}>
                  <td>{new Date(run.started_at).toLocaleString()}</td>
                  <td>{run.published_by}</td>
                  <td><span className={`status-dot ${run.outcome}`}>{run.outcome}</span></td>
                  <td>{run.shows_published}</td>
                  <td>{run.episodes_published}</td>
                  <td>{run.is_current ? '✅' : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

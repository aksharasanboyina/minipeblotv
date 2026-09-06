import { useState, useRef } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../context/AuthContext'

const SPECS: Record<string, { dims: string; size: string }> = {
  poster: { dims: '600 × 900 px (2:3)', size: 'max 200 KB' },
  banner: { dims: '1280 × 720 px (16:9)', size: 'max 200 KB' },
  thumbnail: { dims: '640 × 360 px (16:9)', size: 'max 200 KB' },
}

export default function ArtworkUpload({
  entityType,
  entityId,
  artworkType,
}: {
  entityType: string
  entityId: string
  artworkType: string
}) {
  const queryClient = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [error, setError] = useState<string[]>([])
  const [uploading, setUploading] = useState(false)

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await api.post(
        `/admin/artwork/${entityType}/${entityId}`,
        formData,
        { params: { artwork_type: artworkType } }
      )
      return resp.data
    },
    onSuccess: () => {
      setError([])
      queryClient.invalidateQueries({ queryKey: ['artworks'] })
      if (fileRef.current) fileRef.current.value = ''
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
      if (detail && typeof detail === 'object' && detail.errors) {
        setError(detail.errors)
      } else {
        setError([String(detail || err?.message || 'Upload failed')])
      }
    },
  })

  const handleFile = (file: File | undefined) => {
    if (!file) return
    setPreview(URL.createObjectURL(file))
    setError([])
    setUploading(true)
    uploadMutation.mutate(file, {
      onSettled: () => setUploading(false),
    })
  }

  return (
    <div className="artwork-slot">
      <div className="artwork-label">
        <strong>{artworkType.charAt(0).toUpperCase() + artworkType.slice(1)}</strong>
        <span className="muted">{SPECS[artworkType].dims} · {SPECS[artworkType].size}</span>
      </div>

      <label className="artwork-dropzone">
        {preview ? (
          <img src={preview} alt={`${artworkType} preview`} className="artwork-preview" />
        ) : (
          <div className="dropzone-placeholder">
            <span>📤</span>
            <span>Click to upload {artworkType}</span>
          </div>
        )}
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png"
          onChange={(e) => handleFile(e.target.files?.[0])}
          hidden
        />
      </label>

      {uploading && <div className="alert">Uploading…</div>}

      {error.length > 0 && (
        <div className="alert alert-error artwork-errors">
          {error.map((e, i) => (
            <div key={i}>{e}</div>
          ))}
        </div>
      )}

      {uploadMutation.isSuccess && (
        <div className="alert alert-success">Uploaded ✓</div>
      )}
    </div>
  )
}

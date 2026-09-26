import React, { useState, useEffect, useRef } from 'react';

export default function KnowledgeVaultScreen({ user, onShowAuth }) {
  const [documents, setDocuments] = useState([]);
  const [totalChunks, setTotalChunks] = useState(0);
  const [loading, setLoading] = useState(true);
  const [uploadStatus, setUploadStatus] = useState('');
  const [docToDelete, setDocToDelete] = useState(null); // { filename, chunk_count }
  const [isDeleting, setIsDeleting] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploadDepartment, setUploadDepartment] = useState('general');
  const [uploadClassification, setUploadClassification] = useState('internal');
  const fileInputRef = useRef(null);

  const fetchKnowledgeList = async () => {
    if (!user) {
      setDocuments([]);
      setTotalChunks(0);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const res = await fetch('/knowledge/list', { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        setDocuments(data.documents || []);
        setTotalChunks(data.total_chunks || 0);
      } else if (res.status === 401) {
        setDocuments([]);
        setTotalChunks(0);
      }
    } catch {
      // ignore network errors
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKnowledgeList();
  }, [user?.id]);

  // Handle ESC key to dismiss confirmation popup
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && docToDelete && !isDeleting) {
        setDocToDelete(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [docToDelete, isDeleting]);

  const uploadFile = async (file) => {
    if (!file) return;
    if (!user) {
      if (onShowAuth) onShowAuth();
      return;
    }
    setUploadStatus(`Ingesting ${file.name}…`);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('ingest', 'true');
    formData.append('department', uploadDepartment);
    formData.append('classification_level', uploadClassification);

    try {
      const res = await fetch('/knowledge/upload', {
        method: 'POST',
        credentials: 'include',
        body: formData,
      });
      
      let data = {};
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        try {
          data = await res.json();
        } catch {
          data = {};
        }
      } else {
        const textError = await res.text().catch(() => '');
        data = { detail: textError || res.statusText };
      }

      if (!res.ok) {
        throw new Error(data.detail || data.error || res.statusText || `Server error (${res.status})`);
      }

      const addedChunks = data.chunks_created ?? data.chunk_count ?? 0;
      setUploadStatus(
        `✓ Ingested ${data.filename || file.name} (${addedChunks} chunk${addedChunks === 1 ? '' : 's'} added)`
      );
      fetchKnowledgeList();
      setTimeout(() => setUploadStatus(''), 6000);
    } catch (err) {
      setUploadStatus(`Upload failed: ${err.message}`);
    }
  };

  const handleConfirmDelete = async () => {
    if (!docToDelete || !user) return;
    const filename = docToDelete.filename;
    setIsDeleting(true);

    try {
      const res = await fetch(`/knowledge/${encodeURIComponent(filename)}`, {
        method: 'DELETE',
        credentials: 'include',
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Failed to delete document');

      setDocToDelete(null);
      setUploadStatus(`✓ Successfully removed "${filename}" from Knowledge Vault.`);
      await fetchKnowledgeList();
      setTimeout(() => setUploadStatus(''), 6000);
    } catch (err) {
      setUploadStatus(`Failed to remove document: ${err.message}`);
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = e.dataTransfer?.files;
    if (files && files[0]) {
      uploadFile(files[0]);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  if (!user) {
    return (
      <section className="screen">
        <div className="screen-head">
          <h2 className="screen-title">Knowledge Vault</h2>
          <p className="screen-sub">
            Private on-premises document repository vectorized with local FAISS + BM25 indices.
          </p>
        </div>

        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '60px 20px',
          background: 'rgba(255, 255, 255, 0.02)',
          border: '1px dashed rgba(255, 255, 255, 0.12)',
          borderRadius: '12px',
          marginTop: '20px',
          textAlign: 'center',
        }}>
          <div style={{
            width: '56px',
            height: '56px',
            borderRadius: '50%',
            background: 'rgba(99, 102, 241, 0.15)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '16px',
          }}>
            <svg viewBox="0 0 24 24" width="28" height="28" stroke="#818cf8" fill="none" strokeWidth="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0110 0v4" />
            </svg>
          </div>
          <h3 style={{ fontSize: '18px', fontWeight: '600', marginBottom: '8px', color: 'var(--text-primary, #fff)' }}>
            Authentication Required
          </h3>
          <p style={{ maxWidth: '440px', color: 'var(--text-muted, #94a3b8)', fontSize: '14px', lineHeight: '1.5', marginBottom: '24px' }}>
            Knowledge Vault documents and vector indices are strictly isolated per user account. Please sign in or register to access your private vault.
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onShowAuth}
            style={{
              padding: '10px 24px',
              fontSize: '14px',
              fontWeight: '500',
              borderRadius: '8px',
              cursor: 'pointer',
            }}
          >
            Sign In / Register
          </button>
        </div>
      </section>
    );
  }


  return (
    <section className="screen">
      <div className="screen-head">
        <h2 className="screen-title">Knowledge Vault</h2>
        <p className="screen-sub">
          Uploaded documents are chunked and vectorized into a local FAISS index + BM25 sparse index.
          All embeddings stay on-device.
        </p>
      </div>

      <div
        className={`dropzone ${isDragOver ? 'is-over' : ''}`}
        onClick={() => fileInputRef.current?.click()}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
      >
        <svg className="icon" viewBox="0 0 24 24">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
        <span>Drop files here or click to browse</span>
        <span className="dropzone-hint">
          Supports .txt, .md, .pdf, .docx, and image files (.png, .jpg) via OCR
        </span>
        <input
          type="file"
          ref={fileInputRef}
          onChange={(e) => {
            if (e.target.files?.[0]) uploadFile(e.target.files[0]);
            e.target.value = '';
          }}
          hidden
        />
      </div>

      {/* Department & Classification selectors */}
      <div style={{
        display: 'flex',
        gap: '12px',
        marginTop: '12px',
        flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1, minWidth: '180px' }}>
          <label style={{ fontSize: '12px', color: 'var(--text-muted, #94a3b8)', fontWeight: '500', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Department</label>
          <select
            className="field"
            value={uploadDepartment}
            onChange={(e) => setUploadDepartment(e.target.value)}
            id="upload-department"
          >
            <option value="general">General</option>
            <option value="process">Process</option>
            <option value="maintenance">Maintenance</option>
            <option value="hse">HSE</option>
            <option value="projects">Projects</option>
            <option value="finance">Finance</option>
          </select>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1, minWidth: '180px' }}>
          <label style={{ fontSize: '12px', color: 'var(--text-muted, #94a3b8)', fontWeight: '500', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Classification</label>
          <select
            className="field"
            value={uploadClassification}
            onChange={(e) => setUploadClassification(e.target.value)}
            id="upload-classification"
          >
            <option value="public">Public</option>
            <option value="internal">Internal</option>
            <option value="restricted">Restricted</option>
          </select>
        </div>
      </div>

      {uploadStatus && (
        <div
          className="inline-note"
          style={{ marginTop: '14px', width: '100%', textAlign: 'center' }}
        >
          {uploadStatus}
        </div>
      )}

      <div className="doc-list">
        {loading ? (
          <div className="empty">Loading indexed documents…</div>
        ) : documents.length === 0 ? (
          <div className="empty">
            No documents indexed yet. Upload a file above to add it to the vault.
          </div>
        ) : (
          documents.map((doc, idx) => {
            const fname = doc.filename || doc.source_filename || 'Document';
            return (
              <div key={idx} className="doc-row" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  <svg className="icon icon-sm" viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
                    <path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5z" />
                    <path d="M14 3v5h5" />
                  </svg>
                  <span className="doc-name" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {fname}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexShrink: 0 }}>
                  <span className="doc-chunks">
                    {doc.chunk_count} chunk{doc.chunk_count === 1 ? '' : 's'}
                  </span>
                  <button
                    className="doc-delete-btn"
                    title={`Remove "${fname}" from Knowledge Vault`}
                    onClick={(e) => {
                      e.stopPropagation();
                      setDocToDelete({ filename: fname, chunk_count: doc.chunk_count });
                    }}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: 'var(--text-muted, #888)',
                      cursor: 'pointer',
                      padding: '4px 6px',
                      borderRadius: '4px',
                      display: 'flex',
                      alignItems: 'center',
                      transition: 'color 0.15s, background 0.15s',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.color = '#ef4444';
                      e.currentTarget.style.background = 'rgba(239, 68, 68, 0.15)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.color = 'var(--text-muted, #888)';
                      e.currentTarget.style.background = 'transparent';
                    }}
                  >
                    <svg className="icon icon-sm" viewBox="0 0 24 24" style={{ width: '16px', height: '16px', stroke: 'currentColor', fill: 'none', strokeWidth: '2' }}>
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                      <line x1="10" y1="11" x2="10" y2="17" />
                      <line x1="14" y1="11" x2="14" y2="17" />
                    </svg>
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Platform In-App Confirmation Modal */}
      {docToDelete && (
        <div
          className="confirm-overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget && !isDeleting) {
              setDocToDelete(null);
            }
          }}
        >
          <div className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-modal-title">
            <div className="confirm-header">
              <div className="confirm-icon-box">
                <svg viewBox="0 0 24 24">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                  <line x1="10" y1="11" x2="10" y2="17" />
                  <line x1="14" y1="11" x2="14" y2="17" />
                </svg>
              </div>
              <div className="confirm-title-area">
                <h3 className="confirm-title" id="confirm-modal-title">Remove Document from Vault</h3>
                <p className="confirm-desc">
                  Are you sure you want to remove <span className="confirm-file-badge">{docToDelete.filename}</span> ({docToDelete.chunk_count} chunk{docToDelete.chunk_count === 1 ? '' : 's'})?
                </p>
              </div>
            </div>

            <div className="confirm-warning-box">
              <svg className="icon icon-sm" viewBox="0 0 24 24" style={{ width: '16px', height: '16px', stroke: 'currentColor', fill: 'none', flexShrink: 0 }}>
                <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <span>This will delete its vector embeddings, BM25 keywords, and local file permanently.</span>
            </div>

            <div className="confirm-actions">
              <button
                type="button"
                className="confirm-btn-cancel"
                onClick={() => setDocToDelete(null)}
                disabled={isDeleting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="confirm-btn-danger"
                onClick={handleConfirmDelete}
                disabled={isDeleting}
              >
                {isDeleting ? (
                  <>
                    <span className="auth-spinner" style={{ width: '14px', height: '14px', borderWidth: '2px' }} />
                    <span>Removing…</span>
                  </>
                ) : (
                  <>
                    <svg className="icon icon-sm" viewBox="0 0 24 24" style={{ width: '14px', height: '14px', stroke: 'currentColor', fill: 'none' }}>
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                    </svg>
                    <span>Remove Document</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}


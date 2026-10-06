import React, { useState, useEffect, useRef, useMemo } from 'react';
import SovereignSelect from './SovereignSelect';
import IngestionMachinery from './IngestionMachinery';

const DEPARTMENT_OPTIONS = [
  { value: 'general', label: 'General' },
  { value: 'process', label: 'Process' },
  { value: 'maintenance', label: 'Maintenance' },
  { value: 'hse', label: 'HSE' },
  { value: 'projects', label: 'Projects' },
  { value: 'finance', label: 'Finance' },
];

const CLASSIFICATION_OPTIONS = [
  { value: 'public', label: 'Public' },
  { value: 'internal', label: 'Internal' },
  { value: 'restricted', label: 'Restricted' },
];

export default function KnowledgeVaultScreen({ user, onShowAuth }) {
  const [documents, setDocuments] = useState([]);
  const [totalChunks, setTotalChunks] = useState(0);
  const [loading, setLoading] = useState(true);
  const [uploadStatus, setUploadStatus] = useState('');
  const [ingestionSession, setIngestionSession] = useState(null); // { file, isProcessing, result, error }
  const [activeIngestion, setActiveIngestion] = useState(null); // { filename, stage, status: 'processing'|'done'|'error', errorMsg, chunkCount, dept, classification }
  const [docToDelete, setDocToDelete] = useState(null); // { filename, chunk_count }
  const [isDeleting, setIsDeleting] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploadDepartment, setUploadDepartment] = useState('general');
  const [uploadClassification, setUploadClassification] = useState('internal');
  const fileInputRef = useRef(null);

  const isSuperadmin = user?.role === 'superadmin';
  const userDept = user?.department || 'general';
  const canSelectRestricted = ['superadmin', 'admin', 'approver'].includes(user?.role);

  // Synchronize department when switching users
  useEffect(() => {
    if (!isSuperadmin && userDept) {
      setUploadDepartment(userDept);
    }
  }, [isSuperadmin, userDept]);

  // Ensure regular engineers cannot select restricted
  useEffect(() => {
    if (!canSelectRestricted && uploadClassification === 'restricted') {
      setUploadClassification('internal');
    }
  }, [canSelectRestricted, uploadClassification]);

  const availableClassificationOptions = useMemo(() => {
    if (canSelectRestricted) return CLASSIFICATION_OPTIONS;
    return CLASSIFICATION_OPTIONS.filter((opt) => opt.value !== 'restricted');
  }, [canSelectRestricted]);

  // Ingestion machinery animation toggle - defaults to OFF
  const [enableAnimation, setEnableAnimation] = useState(() => {
    const saved = localStorage.getItem('kavach_vault_animation');
    if (saved !== null) return saved === 'true';
    return (
      import.meta.env.VITE_ENABLE_INGESTION_ANIMATION === 'true' ||
      import.meta.env.VITE_ENABLE_INGESTION_ANIMATION === '1'
    );
  });

  const handleToggleAnimation = () => {
    setEnableAnimation((prev) => {
      const next = !prev;
      localStorage.setItem('kavach_vault_animation', String(next));
      return next;
    });
  };

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

    const effectiveDept = isSuperadmin ? uploadDepartment : userDept;
    const effectiveClass = canSelectRestricted
      ? uploadClassification
      : (uploadClassification === 'restricted' ? 'internal' : uploadClassification);

    setUploadStatus(`Ingesting ${file.name} into on-prem vector vault…`);

    // Always launch prominent real-time Ingestion Line
    setActiveIngestion({
      filename: file.name,
      status: 'processing',
      stage: 'Extracting text, OCR, chunking & generating on-prem embeddings…',
      dept: effectiveDept,
      classification: effectiveClass,
    });

    // Optionally launch rich multi-stage machinery animation if user/env enabled
    if (enableAnimation) {
      setIngestionSession({
        file,
        isProcessing: true,
        result: null,
        error: null,
      });
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('ingest', 'true');
    formData.append('department', effectiveDept);
    formData.append('classification_level', effectiveClass);

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

      // Update real-time Ingestion Line to success state
      setActiveIngestion({
        filename: data.filename || file.name,
        status: 'done',
        stage: 'Successfully indexed into local FAISS + BM25 vector stores',
        chunkCount: addedChunks,
        dept: effectiveDept,
        classification: effectiveClass,
      });

      if (enableAnimation) {
        setIngestionSession((prev) => ({
          ...prev,
          isProcessing: false,
          result: data,
          error: null,
        }));
      }
      fetchKnowledgeList();

      // Auto-clear success message after 8 seconds
      setTimeout(() => {
        setUploadStatus('');
        setActiveIngestion((prev) => (prev?.status === 'done' ? null : prev));
      }, 8000);
    } catch (err) {
      setUploadStatus(`Upload failed: ${err.message}`);
      setActiveIngestion({
        filename: file.name,
        status: 'error',
        errorMsg: err.message,
        dept: effectiveDept,
        classification: effectiveClass,
      });

      if (enableAnimation) {
        setIngestionSession((prev) => ({
          ...prev,
          isProcessing: false,
          result: null,
          error: err.message,
        }));
      }
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
          padding: '48px 24px',
          background: 'var(--bg-card)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          boxShadow: 'var(--shadow-card)',
          marginTop: '20px',
          textAlign: 'center',
        }}>
          <div style={{
            width: '56px',
            height: '56px',
            borderRadius: '50%',
            background: 'rgba(2, 132, 199, 0.12)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '16px',
          }}>
            <svg viewBox="0 0 24 24" width="28" height="28" stroke="#0284c7" fill="none" strokeWidth="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0110 0v4" />
            </svg>
          </div>
          <h3 style={{ fontSize: '18px', fontWeight: '600', marginBottom: '8px', color: 'var(--text-primary)' }}>
            Authentication Required
          </h3>
          <p style={{ maxWidth: '440px', color: 'var(--text-secondary)', fontSize: '14px', lineHeight: '1.5', marginBottom: '24px' }}>
            Knowledge Vault documents and vector indices are strictly isolated per user account. Please sign in or register to access your private vault.
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onShowAuth}
          >
            Sign In / Register
          </button>
        </div>
      </section>
    );
  }


  return (
    <section className="screen">
      <div className="screen-head" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 className="screen-title">Knowledge Vault</h2>
          <p className="screen-sub">
            Uploaded documents are chunked and vectorized into a local FAISS index + BM25 sparse index.
            All embeddings stay on-device.
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            type="button"
            className={`vault-anim-toggle-btn ${enableAnimation ? 'active' : ''}`}
            onClick={handleToggleAnimation}
            title={enableAnimation ? "Machinery animation is ON. Click to disable." : "Machinery animation is OFF (Default). Click to enable."}
            aria-label="Toggle Ingestion Machinery Animation"
          >
            <span className="anim-toggle-dot" />
            <span>Machinery Animation: <strong>{enableAnimation ? 'ON' : 'OFF'}</strong></span>
          </button>
        </div>
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
          {isSuperadmin ? (
            <SovereignSelect
              value={uploadDepartment}
              onChange={(e) => setUploadDepartment(e.target.value)}
              options={DEPARTMENT_OPTIONS}
              id="upload-department"
              placeholder="Select Department"
              ariaLabel="Select Department"
            />
          ) : (
            <div className="vault-locked-dept-pill" title="Upload is strictly locked to your assigned department">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0110 0v4" />
              </svg>
              <span>DEPT: <strong>{userDept.toUpperCase()}</strong></span>
              <span className="locked-badge-sub">• ASSIGNED</span>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flex: 1, minWidth: '180px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <label style={{ fontSize: '12px', color: 'var(--text-muted, #94a3b8)', fontWeight: '500', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Classification</label>
            {!canSelectRestricted && (
              <span style={{ fontSize: '11px', color: '#94a3b8' }}>Restricted requires Supervisor</span>
            )}
          </div>
          <SovereignSelect
            value={uploadClassification}
            onChange={(e) => setUploadClassification(e.target.value)}
            options={availableClassificationOptions}
            id="upload-classification"
            placeholder="Select Classification"
            ariaLabel="Select Classification"
          />
        </div>
      </div>

      {/* Prominent Real-Time Ingestion Line (Shows progress and completion when animation toggle is OFF or ON) */}
      {activeIngestion && (
        <div className={`vault-ingestion-line-card status-${activeIngestion.status}`} role="status">
          <div className="ingestion-line-header">
            <div className="ingestion-line-left">
              {activeIngestion.status === 'processing' && (
                <span className="ingestion-spinner" />
              )}
              {activeIngestion.status === 'done' && (
                <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="#10b981" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              )}
              {activeIngestion.status === 'error' && (
                <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="#ef4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
              )}
              <div className="ingestion-meta">
                <span className="ingestion-filename">{activeIngestion.filename}</span>
                <span className="ingestion-stage">
                  {activeIngestion.status === 'error' ? activeIngestion.errorMsg : activeIngestion.stage}
                </span>
              </div>
            </div>

            <div className="ingestion-line-right">
              {activeIngestion.chunkCount !== undefined && activeIngestion.status === 'done' && (
                <span className="ingestion-chunk-badge">{activeIngestion.chunkCount} chunks added</span>
              )}
              <button
                type="button"
                className="ingestion-close-btn"
                onClick={() => setActiveIngestion(null)}
                title="Dismiss notification"
              >
                &times;
              </button>
            </div>
          </div>

          {activeIngestion.status === 'processing' && (
            <div className="ingestion-progress-track">
              <div className="ingestion-progress-bar animate-scan" />
            </div>
          )}
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

      {ingestionSession && (
        <IngestionMachinery
          file={ingestionSession.file}
          isProcessing={ingestionSession.isProcessing}
          result={ingestionSession.result}
          error={ingestionSession.error}
          onComplete={() => {
            setIngestionSession(null);
            fetchKnowledgeList();
          }}
        />
      )}
    </section>
  );
}


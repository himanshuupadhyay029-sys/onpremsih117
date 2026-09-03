import React, { useState, useEffect, useRef } from 'react';

export default function KnowledgeVaultScreen() {
  const [documents, setDocuments] = useState([]);
  const [totalChunks, setTotalChunks] = useState(0);
  const [loading, setLoading] = useState(true);
  const [uploadStatus, setUploadStatus] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const fetchKnowledgeList = async () => {
    try {
      const res = await fetch('/knowledge/list');
      const data = await res.json();
      setDocuments(data.documents || []);
      setTotalChunks(data.total_chunks || 0);
    } catch {
      // ignore network errors
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKnowledgeList();
  }, []);

  const uploadFile = async (file) => {
    if (!file) return;
    setUploadStatus(`Ingesting ${file.name}…`);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('ingest', 'true');

    try {
      const res = await fetch('/knowledge/upload', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);

      setUploadStatus(
        `✓ Ingested ${data.filename} (${data.chunks_created || 0} chunks added)`
      );
      fetchKnowledgeList();
      setTimeout(() => setUploadStatus(''), 6000);
    } catch (err) {
      setUploadStatus(`Upload failed: ${err.message}`);
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

  return (
    <section className="screen">
      <div className="screen-head">
        <h2 className="screen-title">Knowledge Vault</h2>
        <p className="screen-sub">
          Uploaded documents are chunked and vectorized into a local FAISS index.
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
          Supports .txt, .md, .pdf, and image files (.png, .jpg) via OCR
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
          documents.map((doc, idx) => (
            <div key={idx} className="doc-row">
              <svg className="icon icon-sm" viewBox="0 0 24 24">
                <path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5z" />
                <path d="M14 3v5h5" />
              </svg>
              <span className="doc-name">{doc.filename || doc.source_filename || 'Document'}</span>
              <span className="doc-chunks">
                {doc.chunk_count} chunk{doc.chunk_count === 1 ? '' : 's'}
              </span>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

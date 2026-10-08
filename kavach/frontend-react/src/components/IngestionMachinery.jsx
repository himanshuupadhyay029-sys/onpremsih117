import React, { useState, useEffect } from 'react';

/**
 * IngestionMachinery - Sovereign Autonomous Ingestion & Vectorization Engine.
 * Visualizes a document entering industrial machinery, being sliced into chunks,
 * transformed into floating vector embeddings, and securely locked into the local FAISS index.
 */
export default function IngestionMachinery({
  file,
  isProcessing,
  result,
  error,
  onComplete,
}) {
  const [stage, setStage] = useState(1); // 1: Intake/Scan, 2: Slice/Chunk, 3: Vector Embed, 4: Vault Store, 5: Complete
  const [vectorStreams, setVectorStreams] = useState([]);

  // Generate realistic looking floating vector coordinates
  useEffect(() => {
    const streams = Array.from({ length: 6 }).map((_, i) => ({
      id: i,
      vals: Array.from({ length: 5 })
        .map(() => (Math.random() * 2 - 1).toFixed(3))
        .join(', '),
      left: `${15 + i * 14}%`,
      delay: `${i * 0.25}s`,
    }));
    setVectorStreams(streams);
  }, []);

  // Stage progression logic
  useEffect(() => {
    let t1, t2, t3;
    if (isProcessing) {
      setStage(1);
      // Move from Intake (1) to Laser Chunking (2) after 1.4s
      t1 = setTimeout(() => {
        setStage(2);
      }, 1400);

      // Move from Chunking (2) to Vector Embedding (3) after 3.2s
      t2 = setTimeout(() => {
        setStage(3);
      }, 3200);

      // Move from Embedding (3) to Vault Storing (4) after 5.0s
      t3 = setTimeout(() => {
        setStage(4);
      }, 5000);
    }

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
    };
  }, [isProcessing]);

  // When backend finished successfully
  useEffect(() => {
    if (result && !error) {
      // Ensure we hit stage 4 then 5
      const timer = setTimeout(() => {
        setStage(5);
      }, 600);
      return () => clearTimeout(timer);
    }
  }, [result, error]);

  const fileName = file?.name || 'Document.txt';
  const fileSize = file?.size
    ? file.size < 1024 * 1024
      ? `${(file.size / 1024).toFixed(1)} KB`
      : `${(file.size / (1024 * 1024)).toFixed(1)} MB`
    : 'Unknown size';

  const chunksCount = result?.chunks_created ?? result?.chunk_count ?? 4;

  return (
    <div className="machinery-backdrop">
      <div className="machinery-card">
        {/* Machinery Top Header / Telemetry Bar */}
        <div className="machinery-header">
          <div className="machinery-branding">
            <div className="machinery-led-pulse" />
            <span className="machinery-title">Autonomous Vector Ingestion Machinery</span>
          </div>
          <div className="machinery-tags">
            <span className="machinery-tag">AIR-GAPPED ENGINE</span>
            <span className="machinery-tag">FAISS + BM25</span>
          </div>
        </div>

        {/* Progress Pipeline Stages Tracker */}
        <div className="machinery-pipeline-tracker">
          <div className={`pipe-step ${stage >= 1 ? 'is-active' : ''} ${stage > 1 ? 'is-done' : ''}`}>
            <span className="pipe-dot">1</span>
            <span className="pipe-name">Intake & Scan</span>
          </div>
          <div className="pipe-connector" />
          <div className={`pipe-step ${stage >= 2 ? 'is-active' : ''} ${stage > 2 ? 'is-done' : ''}`}>
            <span className="pipe-dot">2</span>
            <span className="pipe-name">Laser Chunking</span>
          </div>
          <div className="pipe-connector" />
          <div className={`pipe-step ${stage >= 3 ? 'is-active' : ''} ${stage > 3 ? 'is-done' : ''}`}>
            <span className="pipe-dot">3</span>
            <span className="pipe-name">Vector Embeddings</span>
          </div>
          <div className="pipe-connector" />
          <div className={`pipe-step ${stage >= 4 ? 'is-active' : ''} ${stage >= 5 ? 'is-done' : ''}`}>
            <span className="pipe-dot">4</span>
            <span className="pipe-name">Vault Storage</span>
          </div>
        </div>

        {/* The Machinery Chamber Viewport */}
        <div className="machinery-chamber">
          {/* Laser guide lines */}
          <div className="chamber-grid-overlay" />

          {/* STAGE 1: Document Entry & Laser Scanning */}
          {stage === 1 && (
            <div className="chamber-stage stage-intake">
              <div className="machinery-intake-slot">
                <span className="slot-label">FEED INTAKE APERTURE</span>
              </div>

              <div className="intake-document-card">
                <div className="doc-scanner-beam" />
                <div className="doc-header-strip">
                  <svg className="doc-icon" viewBox="0 0 24 24" width="16" height="16">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" fill="none" stroke="currentColor" strokeWidth="2" />
                    <polyline points="14 2 14 8 20 8" fill="none" stroke="currentColor" strokeWidth="2" />
                  </svg>
                  <span className="doc-filename-text" title={fileName}>{fileName}</span>
                  <span className="doc-size-badge">{fileSize}</span>
                </div>
                <div className="doc-simulated-text">
                  <div className="text-line w-80" />
                  <div className="text-line w-100" />
                  <div className="text-line w-90" />
                  <div className="text-line w-75" />
                  <div className="text-line w-95" />
                  <div className="text-line w-60" />
                </div>
              </div>

              <div className="chamber-status-hud">
                <span className="hud-spinner" />
                <span>Ingesting raw document bytes & parsing semantic structure…</span>
              </div>
            </div>
          )}

          {/* STAGE 2: Laser Slicing / Chunking */}
          {stage === 2 && (
            <div className="chamber-stage stage-chunking">
              <div className="laser-cutter-line" />
              <div className="laser-spark spark-left" />
              <div className="laser-spark spark-right" />

              <div className="chunks-container">
                <div className="chunk-slice chunk-1">
                  <div className="chunk-tag">CHUNK 01 · HEADER & SCOPE</div>
                  <div className="chunk-content-preview">SECTION 1.0 OPERATIONAL BYPASS PARAMETERS...</div>
                </div>
                <div className="chunk-slice chunk-2">
                  <div className="chunk-tag">CHUNK 02 · STEPWISE SEQUENCE</div>
                  <div className="chunk-content-preview">STEP 1. ISOLATE SUCTION VALVE V-102. VERIFY 0 PSI...</div>
                </div>
                <div className="chunk-slice chunk-3">
                  <div className="chunk-tag">CHUNK 03 · SAFETY TOLERANCES</div>
                  <div className="chunk-content-preview">CRITICAL INTERLOCK: DISCHARGE PRESSURE NOT TO EXCEED 45 BAR...</div>
                </div>
                <div className="chunk-slice chunk-4">
                  <div className="chunk-tag">CHUNK 04 · VERIFICATION & AUDIT</div>
                  <div className="chunk-content-preview">LOG ENTRY REQUIRED IN DCS LEDGER PRIOR TO ACTUATION...</div>
                </div>
              </div>

              <div className="chamber-status-hud">
                <span className="hud-laser-icon">⚡</span>
                <span>Recursive semantic slicing active · Splitting text into context windows…</span>
              </div>
            </div>
          )}

          {/* STAGE 3: Dense Vector Embeddings Generation */}
          {stage === 3 && (
            <div className="chamber-stage stage-embedding">
              <div className="vector-matrix-cloud">
                {vectorStreams.map((stream) => (
                  <div
                    key={stream.id}
                    className="floating-vector-token"
                    style={{ left: stream.left, animationDelay: stream.delay }}
                  >
                    [{stream.vals}]
                  </div>
                ))}
              </div>

              <div className="embedded-chunks-row">
                <div className="embedded-chunk-card pulse-glow">
                  <span className="emb-label">Chunk #1</span>
                  <span className="emb-tensor">768-D DENSE</span>
                  <div className="emb-bars">
                    <div className="emb-bar" style={{ height: '70%' }} />
                    <div className="emb-bar" style={{ height: '40%' }} />
                    <div className="emb-bar" style={{ height: '90%' }} />
                    <div className="emb-bar" style={{ height: '60%' }} />
                  </div>
                </div>
                <div className="embedded-chunk-card pulse-glow">
                  <span className="emb-label">Chunk #2</span>
                  <span className="emb-tensor">768-D DENSE</span>
                  <div className="emb-bars">
                    <div className="emb-bar" style={{ height: '85%' }} />
                    <div className="emb-bar" style={{ height: '55%' }} />
                    <div className="emb-bar" style={{ height: '65%' }} />
                    <div className="emb-bar" style={{ height: '95%' }} />
                  </div>
                </div>
                <div className="embedded-chunk-card pulse-glow">
                  <span className="emb-label">Chunk #3</span>
                  <span className="emb-tensor">768-D DENSE</span>
                  <div className="emb-bars">
                    <div className="emb-bar" style={{ height: '45%' }} />
                    <div className="emb-bar" style={{ height: '80%' }} />
                    <div className="emb-bar" style={{ height: '70%' }} />
                    <div className="emb-bar" style={{ height: '50%' }} />
                  </div>
                </div>
              </div>

              <div className="chamber-status-hud">
                <span className="hud-spinner" />
                <span>Computing neural embeddings locally · Transforming semantics into tensors…</span>
              </div>
            </div>
          )}

          {/* STAGE 4: Storing in Local FAISS & BM25 Vault */}
          {stage === 4 && (
            <div className="chamber-stage stage-vault-store">
              <div className="vault-safe-door is-closing">
                <div className="vault-gear-spindle" />
                <svg className="vault-shield-icon" viewBox="0 0 24 24" width="48" height="48">
                  <path
                    d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"
                    fill="rgba(2, 132, 199, 0.15)"
                    stroke="#0284c7"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M9 12l2 2 4-4"
                    fill="none"
                    stroke="#0284c7"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>

              <div className="vault-particles-absorb">
                <div className="particle p1" />
                <div className="particle p2" />
                <div className="particle p3" />
                <div className="particle p4" />
              </div>

              <div className="chamber-status-hud">
                <span className="hud-spinner" />
                <span>Writing vectors to local FAISS index & BM25 inverted keyword index…</span>
              </div>
            </div>
          )}

          {/* STAGE 5: Completed & Sealed */}
          {stage === 5 && (
            <div className="chamber-stage stage-completed">
              <div className="completed-success-badge">
                <svg viewBox="0 0 24 24" width="44" height="44" fill="none" stroke="#059669" strokeWidth="2.5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M20 6L9 17l-5-5" />
                </svg>
              </div>

              <h3 className="completed-title">Ingestion & Vectorization Sealed</h3>
              <p className="completed-desc">
                <strong>{fileName}</strong> has been decomposed into <strong>{chunksCount} searchable vector chunks</strong> and committed to the local FAISS index.
              </p>

              <div className="completed-metrics-pills">
                <span className="comp-pill">
                  <strong>{chunksCount}</strong> Chunks
                </span>
                <span className="comp-pill">
                  <strong>768-D</strong> Dense Vectors
                </span>
                <span className="comp-pill">
                  <strong>BM25</strong> Keywords Active
                </span>
                <span className="comp-pill comp-airgap">
                  <strong>0</strong> Network Calls
                </span>
              </div>

              <button
                type="button"
                className="btn btn-primary completed-done-btn"
                onClick={onComplete}
              >
                Return to Knowledge Vault
              </button>
            </div>
          )}

          {/* Error Banner if ingestion failed */}
          {error && (
            <div className="machinery-error-banner">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#ef4444" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <div className="error-text-wrap">
                <strong>Ingestion Error:</strong> {error}
              </div>
              <button type="button" className="btn btn-secondary btn-sm" onClick={onComplete}>
                Close
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

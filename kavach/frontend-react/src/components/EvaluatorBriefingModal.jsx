import React, { useState } from 'react';

export default function EvaluatorBriefingModal({ isOpen, onClose, isFirstVisit = false }) {
  const [dontShowAgain, setDontShowAgain] = useState(true);

  if (!isOpen) return null;

  const handleProceed = () => {
    if (dontShowAgain) {
      sessionStorage.setItem('kavach_briefing_seen', '1');
    }
    onClose();
  };

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget && !isFirstVisit) {
      handleProceed();
    }
  };

  return (
    <div
      className="evaluator-briefing-overlay"
      onClick={handleOverlayClick}
      id="evaluator-briefing-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="briefing-title"
    >
      <div className="evaluator-briefing-modal" id="evaluator-briefing-modal">
        {/* Close button (always enabled, especially when opened from top bar) */}
        <button
          className="briefing-close-btn"
          onClick={handleProceed}
          title="Close briefing"
          aria-label="Close architecture briefing"
        >
          <svg className="icon" viewBox="0 0 24 24">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>

        {/* Header / Authority Badges */}
        <div className="briefing-header">
          <div className="briefing-badge-row">
            <span className="briefing-badge sih-badge">
              <span className="badge-pulse" />
              SIH 2026 · Problem Statement 117 (MRPL)
            </span>
            <span className="briefing-badge sovereign-badge">
              <svg className="icon icon-sm" viewBox="0 0 24 24">
                <path d="M12 3l7 3v5.5c0 4.2-2.9 8.1-7 9.5-4.1-1.4-7-5.3-7-9.5V6l7-3z" />
              </svg>
              Air-Gapped On-Premises Mandate
            </span>
          </div>

          <h1 className="briefing-title" id="briefing-title">
            Architectural Notice for Evaluators
          </h1>
          <p className="briefing-subtitle">
            Why this live cloud deployment exists and how it verifies our 100% on-premises system.
          </p>
        </div>

        {/* Core Narrative / Explanation Grid */}
        <div className="briefing-content">
          {/* Section 1: The Context */}
          <div className="briefing-card briefing-mandate-card">
            <div className="briefing-card-icon mandate-icon">
              <svg viewBox="0 0 24 24" className="icon">
                <rect x="2" y="7" width="20" height="14" rx="2" ry="2" />
                <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
              </svg>
            </div>
            <div className="briefing-card-text">
              <h3>The Mandate &amp; The Cloud Confusion</h3>
              <p>
                <strong>SIH Problem Statement 117 (MRPL)</strong> demands a strictly air-gapped, zero-leakage autonomous AI assistant for critical refinery operations. 
                Because external judges cannot physically access our private on-premises GPU workstation over the internet, we deployed this live cloud mirror so evaluators can immediately test the assistant from any browser.
              </p>
            </div>
          </div>

          {/* Section 2: Architecture Comparison Matrix */}
          <div className="briefing-comparison-grid">
            {/* Column 1: The Real Physical Hardware Setup */}
            <div className="comparison-col col-onprem">
              <div className="comparison-header">
                <span className="col-status-pill status-onprem">
                  <svg className="icon icon-sm" viewBox="0 0 24 24">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  Physical Workstation (Our Real Rig)
                </span>
                <h4>100% On-Premises &amp; Air-Gapped</h4>
              </div>
              <ul className="comparison-list">
                <li>
                  <span className="list-bullet">✓</span>
                  <div>
                    <strong>Local LLM Inference:</strong> Runs on local Ollama (<code>Qwen2.5-3B</code>, <code>Qwen2.5-Coder</code>, <code>Moondream</code>) directly on local hardware.
                  </div>
                </li>
                <li>
                  <span className="list-bullet">✓</span>
                  <div>
                    <strong>Hardware Firewall Lockdown:</strong> Enforces OS default-deny firewall (Windows Filtering Platform / iptables) blocking all external egress.
                  </div>
                </li>
                <li>
                  <span className="list-bullet">✓</span>
                  <div>
                    <strong>Isolated Docker Sandbox:</strong> Python sandbox execution isolated with <code>--network none</code>.
                  </div>
                </li>
                <li>
                  <span className="list-bullet">✓</span>
                  <div>
                    <strong>Offline Knowledge Vault:</strong> Local FAISS + BM25 vector indices stored securely on-device.
                  </div>
                </li>
              </ul>
            </div>

            {/* Column 2: This Live Web Evaluation Link */}
            <div className="comparison-col col-cloud">
              <div className="comparison-header">
                <span className="col-status-pill status-cloud">
                  <svg className="icon icon-sm" viewBox="0 0 24 24">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="2" y1="12" x2="22" y2="12" />
                  </svg>
                  This Live Web Link (Evaluator Preview)
                </span>
                <h4>Remote Evaluation Bridge</h4>
              </div>
              <ul className="comparison-list">
                <li>
                  <span className="list-bullet">ℹ</span>
                  <div>
                    <strong>Evaluation Bridge:</strong> Uses remote model fallback so remote judges can test agentic workflows simultaneously without local setup.
                  </div>
                </li>
                <li>
                  <span className="list-bullet">ℹ</span>
                  <div>
                    <strong>Identical Agentic Engine:</strong> Runs the exact same planning loop, Knowledge Vault RAG, and document rendering pipelines.
                  </div>
                </li>
                <li>
                  <span className="list-bullet">ℹ</span>
                  <div>
                    <strong>Audit &amp; Human Approval:</strong> Full audit trail, immutable logs, and human-in-the-loop document approval workflow intact.
                  </div>
                </li>
                <li>
                  <span className="list-bullet">ℹ</span>
                  <div>
                    <strong>Telemetry Simulator:</strong> Live connection telemetry and hardware firewall toggles remain interactive for inspection.
                  </div>
                </li>
              </ul>
            </div>
          </div>

          {/* Proof Badges Row */}
          <div className="briefing-proof-strip">
            <div className="proof-pill">
              <span className="proof-icon">🛡️</span>
              <span>100% Offline Architecture</span>
            </div>
            <div className="proof-pill">
              <span className="proof-icon">⚡</span>
              <span>Zero Cloud Dependency in Prod</span>
            </div>
            <div className="proof-pill">
              <span className="proof-icon">🔒</span>
              <span>Docker &lsquo;--network none&rsquo; Sandbox</span>
            </div>
            <div className="proof-pill">
              <span className="proof-icon">📑</span>
              <span>Local FAISS + BM25 Vault</span>
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="briefing-footer">
          <label className="briefing-checkbox-label">
            <input
              type="checkbox"
              checked={dontShowAgain}
              onChange={(e) => setDontShowAgain(e.target.checked)}
            />
            <span>Don&rsquo;t show this notice automatically again this session</span>
          </label>

          <button
            className="btn-launch-demo"
            onClick={handleProceed}
            id="btn-launch-demo"
          >
            <span>Proceed to Sovereign Workspace</span>
            <svg className="icon" viewBox="0 0 24 24">
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="12 5 19 12 12 19" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

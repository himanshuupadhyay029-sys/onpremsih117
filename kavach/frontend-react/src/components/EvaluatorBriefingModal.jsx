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
        {/* Close button */}
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
            Demo Preview — Runs 100% On-Premises in Production
          </h1>
          <p className="briefing-subtitle">
            Judges cannot access our private GPU workstation remotely, so this cloud mirror lets you test the full agentic system from any browser.
          </p>
        </div>

        {/* Compact 3-column icon grid */}
        <div className="briefing-content">
          <div className="briefing-icon-grid">

            {/* Card 1 — On-Prem Production */}
            <div className="briefing-icon-card">
              <div className="bic-icon bic-icon--green">
                <svg viewBox="0 0 24 24" className="icon">
                  <path d="M12 3l7 3v5.5c0 4.2-2.9 8.1-7 9.5-4.1-1.4-7-5.3-7-9.5V6l7-3z" />
                </svg>
              </div>
              <h4 className="bic-title">Air-Gapped on Production</h4>
              <p className="bic-desc">
                Real system runs with hardware firewall, Docker <code>--network none</code> sandbox, and zero external egress.
              </p>
            </div>

            {/* Card 2 — Demo via HuggingFace */}
            <div className="briefing-icon-card">
              <div className="bic-icon bic-icon--blue">
                <svg viewBox="0 0 24 24" className="icon">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="2" y1="12" x2="22" y2="12" />
                  <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
                </svg>
              </div>
              <h4 className="bic-title">Demo Uses HuggingFace</h4>
              <p className="bic-desc">
                This live link uses HF Inference API as a remote fallback so judges can test workflows without local GPU setup.
              </p>
            </div>

            {/* Card 3 — Identical Engine */}
            <div className="briefing-icon-card">
              <div className="bic-icon bic-icon--amber">
                <svg viewBox="0 0 24 24" className="icon">
                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                </svg>
              </div>
              <h4 className="bic-title">Identical Agentic Engine</h4>
              <p className="bic-desc">
                Same LangGraph planner, FAISS Knowledge Vault, audit trail, and Human Approval Gate — only model source differs.
              </p>
            </div>

          </div>

          {/* Model Provenance Strip */}
          <div className="briefing-model-strip">
            <div className="bms-header">
              <svg viewBox="0 0 24 24" className="icon icon-sm">
                <rect x="2" y="3" width="20" height="14" rx="2" />
                <line x1="8" y1="21" x2="16" y2="21" />
                <line x1="12" y1="17" x2="12" y2="21" />
              </svg>
              <span>On-Premises Production Models</span>
              <span className="bms-note">(local Ollama — no internet)</span>
            </div>

            <div className="bms-model-rows">
              <div className="bms-model-row">
                <span className="bms-flag">🇺🇸</span>
                <code className="bms-model-name">gemma3:4b</code>
                <span className="bms-role-badge bms-role--reason">Reasoning · Vision</span>
                <span className="bms-origin">Google DeepMind</span>
              </div>
              <div className="bms-model-row">
                <span className="bms-flag">🇺🇸</span>
                <code className="bms-model-name">granite4.1:3b</code>
                <span className="bms-role-badge bms-role--code">Code</span>
                <span className="bms-origin">IBM Research</span>
              </div>
              <div className="bms-model-row">
                <span className="bms-flag">🇺🇸</span>
                <code className="bms-model-name">nomic-embed-text</code>
                <span className="bms-role-badge bms-role--embed">Embeddings</span>
                <span className="bms-origin">Nomic AI</span>
              </div>
            </div>

            <div className="bms-status-chips">
              <span className="bms-chip bms-chip--safe">
                <svg viewBox="0 0 24 24" className="icon" style={{width:'13px',height:'13px'}}>
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                USA / EU Origin Only
              </span>
              <span className="bms-chip bms-chip--danger">
                <svg viewBox="0 0 24 24" className="icon" style={{width:'13px',height:'13px'}}>
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
                No Chinese Models in Production
              </span>
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
            <span>Enter Sovereign Workspace</span>
            <span className="btn-scroll-icon" aria-hidden="true">
              <svg className="icon" viewBox="0 0 24 24">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}

import React, { useState, useEffect, useRef, useCallback } from 'react';

export default function EvaluatorBriefingModal({ isOpen, onClose }) {
  const [dragOffset, setDragOffset] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [isUnlocked, setIsUnlocked] = useState(false);

  const trackRef = useRef(null);
  const startXRef = useRef(0);
  const maxSlideRef = useRef(0);

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setDragOffset(0);
      setIsDragging(false);
      setIsUnlocked(false);
    }
  }, [isOpen]);

  // Recalculate max draggable distance
  const updateMaxSlide = useCallback(() => {
    if (trackRef.current) {
      const trackWidth = trackRef.current.clientWidth;
      const thumbWidth = 44; // Thumb width in px
      const padding = 8; // Left/right padding
      maxSlideRef.current = Math.max(0, trackWidth - thumbWidth - padding);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      updateMaxSlide();
      window.addEventListener('resize', updateMaxSlide);
      return () => window.removeEventListener('resize', updateMaxSlide);
    }
  }, [isOpen, updateMaxSlide]);

  if (!isOpen) return null;

  const handlePointerDown = (e) => {
    if (isUnlocked) return;
    updateMaxSlide();
    setIsDragging(true);
    startXRef.current = e.clientX - dragOffset;
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // ignore
    }
  };

  const handlePointerMove = (e) => {
    if (!isDragging || isUnlocked) return;
    const currentX = e.clientX;
    const rawOffset = currentX - startXRef.current;
    const max = maxSlideRef.current || 200;
    const clamped = Math.max(0, Math.min(rawOffset, max));
    setDragOffset(clamped);
  };

  const handlePointerUp = (e) => {
    if (!isDragging || isUnlocked) return;
    setIsDragging(false);
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      // ignore
    }

    const max = maxSlideRef.current || 200;
    const progress = max > 0 ? dragOffset / max : 0;

    // Threshold: 82% of total track distance
    if (progress >= 0.82) {
      setIsUnlocked(true);
      setDragOffset(max);
      setTimeout(() => {
        onClose();
      }, 360);
    } else {
      // Snap back smoothly to start
      setDragOffset(0);
    }
  };

  const max = maxSlideRef.current || 200;
  const progress = max > 0 ? dragOffset / max : 0;
  const fillWidth = dragOffset > 0 ? `calc(${dragOffset}px + 44px)` : '0%';
  const textOpacity = Math.max(0, 1 - progress * 1.5);

  return (
    <div
      className="evaluator-briefing-overlay"
      id="evaluator-briefing-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="briefing-title"
    >
      <div className="evaluator-briefing-modal" id="evaluator-briefing-modal">

        {/* Header */}
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
        </div>

        {/* 3-column icon grid + model strip */}
        <div className="briefing-content">
          <div className="briefing-icon-grid">

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
                This web demo uses HuggingFace serverless inference (<code>Qwen2.5-7B</code>, <code>Granite-3.3-8B</code>, <code>Qwen2-VL</code>) so evaluators can test live workflows without local GPU hardware.
              </p>
            </div>

            <div className="briefing-icon-card">
              <div className="bic-icon bic-icon--amber">
                <svg viewBox="0 0 24 24" className="icon">
                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                </svg>
              </div>
              <h4 className="bic-title">Identical Agentic Engine</h4>
              <p className="bic-desc">
                Same LangGraph planner, FAISS Knowledge Vault, audit trail, and Human Approval Gate — on-premises production runs strictly on local Ollama.
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
              <span className="bms-note">(Local Ollama on-prem · Cloud demo falls back to HF equivalents)</span>
            </div>

            <div className="bms-model-rows">
              <div className="bms-model-row">
                <span className="bms-flag">🇺🇸</span>
                <code className="bms-model-name">gemma3:4b</code>
                <span className="bms-role-badge bms-role--reason">Reasoning · Vision</span>
                <span className="bms-origin">Local Ollama (Cloud: Qwen2.5-7B / Qwen2-VL)</span>
              </div>
              <div className="bms-model-row">
                <span className="bms-flag">🇺🇸</span>
                <code className="bms-model-name">granite4.1:3b</code>
                <span className="bms-role-badge bms-role--code">Code</span>
                <span className="bms-origin">Local Ollama (Cloud: Granite-3.3-8B)</span>
              </div>
              <div className="bms-model-row">
                <span className="bms-flag">🇺🇸</span>
                <code className="bms-model-name">nomic-embed-text</code>
                <span className="bms-role-badge bms-role--embed">Embeddings</span>
                <span className="bms-origin">Local FAISS (Cloud: nomic-embed-v1.5)</span>
              </div>
            </div>

            <div className="bms-status-chips">
              <span className="bms-chip bms-chip--safe">
                <svg viewBox="0 0 24 24" className="icon" style={{ width: '13px', height: '13px' }}>
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                USA / EU Origin Only
              </span>
              <span className="bms-chip bms-chip--danger">
                <svg viewBox="0 0 24 24" className="icon" style={{ width: '13px', height: '13px' }}>
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
                No Chinese Models in Production
              </span>
            </div>
          </div>
        </div>

        {/* Footer with Draggable Slide-to-Unlock Slider */}
        <div className="briefing-footer briefing-footer-centered">
          <div
            ref={trackRef}
            className={`briefing-slide-track ${isDragging ? 'is-dragging' : ''} ${isUnlocked ? 'slide-unlocked' : ''}`}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerUp}
            role="slider"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(progress * 100)}
            aria-label="Slide to enter sovereign workspace"
            id="btn-enter-workspace"
          >
            {/* Dynamic Green Sweep Fill tracking slider position */}
            <div
              className="bst-fill"
              style={{
                width: fillWidth,
                transition: isDragging ? 'none' : 'width 0.28s cubic-bezier(0.25, 1, 0.5, 1)',
              }}
            />

            {/* Draggable Thumb */}
            <div
              className="bst-thumb"
              style={{
                transform: `translateX(${dragOffset}px)`,
                transition: isDragging ? 'none' : 'transform 0.28s cubic-bezier(0.25, 1, 0.5, 1)',
              }}
              aria-hidden="true"
            >
              {isUnlocked ? (
                <svg viewBox="0 0 24 24" className="bst-thumb-icon bst-thumb-icon-success">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              ) : (
                <svg viewBox="0 0 24 24" className="bst-thumb-icon">
                  <line x1="5" y1="12" x2="19" y2="12" />
                  <polyline points="12 5 19 12 12 19" />
                </svg>
              )}
            </div>

            {/* Centered Label text */}
            <span
              className="bst-label"
              style={{ opacity: isUnlocked ? 1 : textOpacity }}
            >
              {isUnlocked ? 'Verified · Entering Workspace…' : 'Slide to Enter Sovereign Workspace →'}
            </span>

            {/* Idle subtle guidance indicator */}
            {!isDragging && !isUnlocked && dragOffset === 0 && (
              <span className="bst-arrow" aria-hidden="true">→</span>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}

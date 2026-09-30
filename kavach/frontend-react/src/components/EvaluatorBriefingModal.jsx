import React, { useState, useRef, useEffect } from 'react';

export default function EvaluatorBriefingModal({ isOpen, onClose, isFirstVisit = false }) {
  const [dontShowAgain, setDontShowAgain] = useState(true);
  const [slideProgress, setSlideProgress] = useState(0); // 0 to 100%
  const [isDragging, setIsDragging] = useState(false);
  const [isUnlocked, setIsUnlocked] = useState(false);

  const trackRef = useRef(null);
  const thumbRef = useRef(null);
  const dragStartX = useRef(0);
  const startProgress = useRef(0);

  useEffect(() => {
    if (!isOpen) {
      setSlideProgress(0);
      setIsDragging(false);
      setIsUnlocked(false);
    }
  }, [isOpen]);

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

  const triggerUnlock = () => {
    setIsUnlocked(true);
    setSlideProgress(100);
    setIsDragging(false);
    setTimeout(() => {
      handleProceed();
    }, 350);
  };

  // --- Drag & Swipe Handlers ---
  const handleDragStart = (clientX) => {
    if (isUnlocked) return;
    setIsDragging(true);
    dragStartX.current = clientX;
    startProgress.current = slideProgress;
  };

  const handleDragMove = (clientX) => {
    if (!isDragging || isUnlocked || !trackRef.current || !thumbRef.current) return;
    const trackRect = trackRef.current.getBoundingClientRect();
    const thumbWidth = thumbRef.current.offsetWidth || 48;
    const maxDistance = trackRect.width - thumbWidth;
    if (maxDistance <= 0) return;

    const deltaX = clientX - dragStartX.current;
    const newProgress = Math.min(Math.max((deltaX / maxDistance) * 100, 0), 100);
    setSlideProgress(newProgress);

    if (newProgress >= 80) {
      triggerUnlock();
    }
  };

  const handleDragEnd = () => {
    if (isUnlocked) return;
    setIsDragging(false);
    if (slideProgress >= 70) {
      triggerUnlock();
    } else {
      setSlideProgress(0); // Snap back smoothly
    }
  };

  // Global mouse up / touch end listener when dragging
  const onMouseDown = (e) => {
    e.preventDefault();
    handleDragStart(e.clientX);
  };

  const onMouseMove = (e) => {
    if (isDragging) {
      handleDragMove(e.clientX);
    }
  };

  const onMouseUp = () => {
    if (isDragging) {
      handleDragEnd();
    }
  };

  const onTouchStart = (e) => {
    if (e.touches.length > 0) {
      handleDragStart(e.touches[0].clientX);
    }
  };

  const onTouchMove = (e) => {
    if (e.touches.length > 0) {
      handleDragMove(e.touches[0].clientX);
    }
  };

  const onTouchEnd = () => {
    handleDragEnd();
  };

  // Click on track directly to auto-slide & unlock
  const handleTrackClick = (e) => {
    if (isUnlocked || isDragging) return;
    triggerUnlock();
  };

  return (
    <div
      className="evaluator-briefing-overlay"
      onClick={handleOverlayClick}
      id="evaluator-briefing-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="briefing-title"
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
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

        {/* Footer Actions with Interactive Slide-from-Left-to-Right Button */}
        <div className="briefing-footer">
          <label className="briefing-checkbox-label">
            <input
              type="checkbox"
              checked={dontShowAgain}
              onChange={(e) => setDontShowAgain(e.target.checked)}
            />
            <span>Don&rsquo;t show this notice automatically again this session</span>
          </label>

          {/* Interactive Slide Track */}
          <div
            className={`briefing-slide-track ${isUnlocked ? 'slide-unlocked' : ''} ${isDragging ? 'slide-dragging' : ''}`}
            ref={trackRef}
            onClick={handleTrackClick}
            role="button"
            tabIndex={0}
            aria-label="Slide or click to enter sovereign workspace"
          >
            {/* Background Fill showing progress */}
            <div
              className="briefing-slide-fill"
              style={{
                width: `${slideProgress}%`,
                transition: isDragging ? 'none' : 'width 0.28s cubic-bezier(0.2, 0.9, 0.3, 1)'
              }}
            />

            {/* Shimmering Animated Text */}
            <div className="briefing-slide-text" style={{ opacity: Math.max(1 - (slideProgress / 60), 0.15) }}>
              <span className="slide-text-shimmer">Slide to Enter Workspace</span>
              <span className="slide-chevrons">›››</span>
            </div>

            {/* Draggable Slider Thumb */}
            <div
              className="briefing-slide-thumb"
              ref={thumbRef}
              style={{
                transform: `translateX(${slideProgress}%)`,
                transition: isDragging ? 'none' : 'transform 0.28s cubic-bezier(0.2, 0.9, 0.3, 1)'
              }}
              onMouseDown={onMouseDown}
              onTouchStart={onTouchStart}
              onTouchMove={onTouchMove}
              onTouchEnd={onTouchEnd}
            >
              {isUnlocked ? (
                <svg className="thumb-icon thumb-icon-check" viewBox="0 0 24 24">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              ) : (
                <svg className="thumb-icon thumb-icon-arrow" viewBox="0 0 24 24">
                  <line x1="5" y1="12" x2="19" y2="12" />
                  <polyline points="12 5 19 12 12 19" />
                </svg>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

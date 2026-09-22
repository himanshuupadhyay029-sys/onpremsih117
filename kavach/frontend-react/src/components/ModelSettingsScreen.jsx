import React, { useState, useEffect, useRef, useMemo } from 'react';

const API_BASE = '';

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

export default function ModelSettingsScreen() {
  const [registry, setRegistry] = useState({});
  const [installedModels, setInstalledModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Model discovery & selection states
  const [pullModelName, setPullModelName] = useState('');
  const [isChecking, setIsChecking] = useState(false);
  const [modelInfo, setModelInfo] = useState(null);
  const [selectedTag, setSelectedTag] = useState('');
  const [tagFilter, setTagFilter] = useState('all');

  // Pull progress & cancellation states
  const [isPulling, setIsPulling] = useState(false);
  const [pullStatus, setPullStatus] = useState('');
  const [pullProgress, setPullProgress] = useState(0);
  const [completedBytes, setCompletedBytes] = useState(0);
  const [totalBytes, setTotalBytes] = useState(0);
  const [pullError, setPullError] = useState(null);
  const [pullSuccess, setPullSuccess] = useState(false);

  const abortControllerRef = useRef(null);

  useEffect(() => {
    fetchModels();
  }, []);

  // Debounced check for model availability in Ollama registry
  useEffect(() => {
    const trimmed = pullModelName.trim();
    if (!trimmed) {
      setModelInfo(null);
      setSelectedTag('');
      setIsChecking(false);
      return;
    }

    const timer = setTimeout(() => {
      checkModelAvailability(trimmed);
    }, 450);

    return () => clearTimeout(timer);
  }, [pullModelName]);

  const fetchModels = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`${API_BASE}/models`);
      if (!res.ok) throw new Error('Failed to fetch models');
      const data = await res.json();
      setRegistry(data.registry || {});
      setInstalledModels(data.installed || []);
      if (data.warning) {
        setError(data.warning);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const checkModelAvailability = async (name) => {
    try {
      setIsChecking(true);
      const res = await fetch(`${API_BASE}/models/info?model=${encodeURIComponent(name)}`);
      if (!res.ok) throw new Error('Failed to query model registry');
      const data = await res.json();
      setModelInfo(data);

      if (data.available && data.tags && data.tags.length > 0) {
        // Auto-select latest or first recommended variant
        const preferred = data.tags.find(t => t.tag === 'latest') || data.tags[0];
        setSelectedTag(preferred.full_name);
      } else {
        setSelectedTag(name);
      }
    } catch (err) {
      setModelInfo({ available: false, error: err.message, tags: [] });
    } finally {
      setIsChecking(false);
    }
  };

  const handleAssign = async (role, modelName) => {
    try {
      const res = await fetch(`${API_BASE}/models/assign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, model: modelName })
      });
      if (!res.ok) throw new Error('Failed to assign model');
      const data = await res.json();
      setRegistry(data.registry);
    } catch (err) {
      alert(err.message);
    }
  };

  const handleDelete = async (modelName) => {
    if (!confirm(`Are you sure you want to delete ${modelName}?`)) return;
    try {
      const res = await fetch(`${API_BASE}/models/${encodeURIComponent(modelName)}`, {
        method: 'DELETE'
      });
      if (!res.ok) throw new Error('Failed to delete model');
      await fetchModels();
    } catch (err) {
      alert(err.message);
    }
  };

  const handleStartPull = async (e) => {
    if (e) e.preventDefault();
    const targetModel = (selectedTag || pullModelName).trim();
    if (!targetModel || isPulling) return;

    setIsPulling(true);
    setPullStatus('Connecting to Ollama...');
    setPullProgress(0);
    setCompletedBytes(0);
    setTotalBytes(0);
    setPullError(null);
    setPullSuccess(false);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await fetch(`${API_BASE}/models/pull/stream?model=${encodeURIComponent(targetModel)}`, {
        signal: controller.signal
      });

      if (!response.ok) {
        throw new Error(`Server returned error status ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // save incomplete line

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.status) {
                setPullStatus(data.status);
              }
              if (data.total && data.total > 0) {
                setTotalBytes(data.total);
                setCompletedBytes(data.completed || 0);
                const pct = Math.min(100, Math.round((data.completed / data.total) * 100));
                setPullProgress(pct);
              }
              if (data.status === 'success') {
                setPullProgress(100);
                setPullStatus('Pull completed successfully!');
                setPullSuccess(true);
                await fetchModels();
              }
              if (data.error) {
                throw new Error(data.error);
              }
            } catch (parseErr) {
              if (parseErr.message && !parseErr.message.includes('Unexpected')) {
                throw parseErr;
              }
            }
          }
        }
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        setPullStatus('Download stopped by user.');
      } else {
        setPullError(err.message || 'Failed to pull model');
      }
    } finally {
      setIsPulling(false);
      abortControllerRef.current = null;
    }
  };

  const handleStopPull = async () => {
    // 1. Abort local fetch stream
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    // 2. Request backend to terminate Ollama connection
    const targetModel = (selectedTag || pullModelName).trim();
    if (targetModel) {
      try {
        await fetch(`${API_BASE}/models/pull/cancel`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ model: targetModel })
        });
      } catch (e) {
        console.warn('Backend cancel failed:', e);
      }
    }

    setIsPulling(false);
    setPullStatus('Download stopped by user.');
  };

  // Filter available tags by quantization type
  const filteredTags = useMemo(() => {
    if (!modelInfo?.tags) return [];
    if (tagFilter === 'all') return modelInfo.tags;
    if (tagFilter === 'q4') {
      return modelInfo.tags.filter(t => t.quantization.includes('Q4') || t.tag.toLowerCase().includes('q4'));
    }
    if (tagFilter === 'q8') {
      return modelInfo.tags.filter(t => t.quantization.includes('Q8') || t.tag.toLowerCase().includes('q8'));
    }
    if (tagFilter === 'fp16') {
      return modelInfo.tags.filter(t => t.quantization.includes('FP16') || t.tag.toLowerCase().includes('fp16') || t.tag.toLowerCase().includes('f16'));
    }
    return modelInfo.tags;
  }, [modelInfo, tagFilter]);

  const selectedTagDetails = useMemo(() => {
    if (!modelInfo?.tags) return null;
    return modelInfo.tags.find(t => t.full_name === selectedTag);
  }, [modelInfo, selectedTag]);

  if (loading) {
    return <div className="screen-content"><div className="loader"></div></div>;
  }

  const roles = ['reasoning', 'code', 'vision', 'embedding', 'rerank'];

  return (
    <div className="screen-content model-settings-screen">
      <header className="screen-header">
        <h2>Model Settings</h2>
        <p className="screen-desc">Manage local Ollama models, download specific quantized variants, and assign roles.</p>
      </header>
      
      {error && <div className="error-banner">{error}</div>}

      {/* Role Assignments Section */}
      <div className="settings-section">
        <h3>Role Assignments</h3>
        <p className="section-desc">Select which installed model should handle each type of task.</p>
        
        <div className="role-assignments-grid">
          {roles.map(role => (
            <div className="role-row" key={role}>
              <div className="role-label">{role.charAt(0).toUpperCase() + role.slice(1)}</div>
              <select 
                className="role-select" 
                value={registry[role] || ''}
                onChange={(e) => handleAssign(role, e.target.value)}
              >
                <option value="" disabled>Select a model...</option>
                {registry[role] && !installedModels.includes(registry[role]) && (
                  <option value={registry[role]}>{registry[role]} (Not Installed)</option>
                )}
                {installedModels.map(m => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </div>

      {/* Installed Models Section */}
      <div className="settings-section">
        <h3>Installed Models</h3>
        <p className="section-desc">Models currently downloaded and available in your local Ollama instance.</p>
        
        {installedModels.length === 0 ? (
          <p className="empty-state">No models installed.</p>
        ) : (
          <ul className="installed-models-list">
            {installedModels.map(m => (
              <li key={m} className="installed-model-item">
                <span className="model-name">{m}</span>
                <button 
                  className="btn btn-sm btn-danger" 
                  onClick={() => handleDelete(m)}
                  title="Delete Model"
                >
                  <svg className="icon" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" fill="none">
                    <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"></path>
                  </svg>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Interactive Model Search, Quantized Selection & Streaming Pull Section */}
      <div className="settings-section pull-section">
        <h3>Pull New Model</h3>
        <p className="section-desc">
          Search for any model in the Ollama library. Check availability, choose your preferred quantized size, and track live download progress.
        </p>
        
        {/* Model Search Input */}
        <div className="model-search-bar">
          <div className="search-input-wrapper">
            <svg className="search-icon" viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" fill="none">
              <circle cx="11" cy="11" r="8" strokeWidth="2"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65" strokeWidth="2" strokeLinecap="round"></line>
            </svg>
            <input 
              type="text" 
              className="input-field model-input" 
              placeholder="Type model name (e.g., gemma3, granite4.1, llama3, mistral)..." 
              value={pullModelName}
              onChange={(e) => setPullModelName(e.target.value)}
              disabled={isPulling}
            />
            {isChecking && <span className="input-spinner"></span>}
          </div>
          <button 
            type="button" 
            className="btn btn-secondary check-btn"
            onClick={() => pullModelName.trim() && checkModelAvailability(pullModelName.trim())}
            disabled={isChecking || !pullModelName.trim() || isPulling}
          >
            Check Availability
          </button>
        </div>

        {/* Availability Badge / Status */}
        {pullModelName.trim() && (
          <div className="availability-status-container">
            {isChecking ? (
              <div className="status-pill status-checking">
                <span className="spinner-tiny"></span> Querying Ollama registry for &ldquo;{pullModelName}&rdquo;...
              </div>
            ) : modelInfo ? (
              modelInfo.available ? (
                <div className="status-pill status-available">
                  <span className="pill-dot green"></span>
                  <strong>{modelInfo.base_name}</strong> is available in Ollama library ({modelInfo.total_tags} tags found)
                </div>
              ) : (
                <div className="status-pill status-not-available">
                  <span className="pill-dot red"></span>
                  {modelInfo.error || `Model "${pullModelName}" not found in Ollama library.`}
                </div>
              )
            ) : null}
          </div>
        )}

        {/* Quantized Size & Variant Selection */}
        {modelInfo?.available && modelInfo.tags?.length > 0 && (
          <div className="quant-selection-panel">
            <div className="quant-panel-header">
              <h4>Select Quantized Size / Variant:</h4>
              <div className="filter-chips">
                <button 
                  type="button" 
                  className={`chip ${tagFilter === 'all' ? 'active' : ''}`} 
                  onClick={() => setTagFilter('all')}
                >
                  All ({modelInfo.tags.length})
                </button>
                <button 
                  type="button" 
                  className={`chip ${tagFilter === 'q4' ? 'active' : ''}`} 
                  onClick={() => setTagFilter('q4')}
                >
                  Q4 (Balanced)
                </button>
                <button 
                  type="button" 
                  className={`chip ${tagFilter === 'q8' ? 'active' : ''}`} 
                  onClick={() => setTagFilter('q8')}
                >
                  Q8 (High Precision)
                </button>
                <button 
                  type="button" 
                  className={`chip ${tagFilter === 'fp16' ? 'active' : ''}`} 
                  onClick={() => setTagFilter('fp16')}
                >
                  FP16 (Full Precision)
                </button>
              </div>
            </div>

            <div className="quant-selector-row">
              <select 
                className="role-select tag-dropdown"
                value={selectedTag}
                onChange={(e) => setSelectedTag(e.target.value)}
                disabled={isPulling}
              >
                {filteredTags.map((t) => (
                  <option key={t.full_name} value={t.full_name}>
                    {t.tag} &nbsp;•&nbsp; [{t.quantization}] &nbsp;•&nbsp; {t.size}
                  </option>
                ))}
              </select>
            </div>

            {/* Selected Summary Card */}
            {selectedTagDetails && (
              <div className="selected-summary-card">
                <div className="summary-col">
                  <span className="summary-label">Target Model Tag</span>
                  <span className="summary-val mono-highlight">{selectedTagDetails.full_name}</span>
                </div>
                <div className="summary-col">
                  <span className="summary-label">Quantization</span>
                  <span className="summary-badge">{selectedTagDetails.quantization}</span>
                </div>
                <div className="summary-col">
                  <span className="summary-label">Download Size</span>
                  <span className="summary-val font-semibold">{selectedTagDetails.size}</span>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Action Controls & Progress Bar */}
        <div className="pull-action-area">
          {!isPulling ? (
            <button 
              type="button" 
              className="btn btn-primary start-pull-btn" 
              onClick={handleStartPull}
              disabled={!(selectedTag || pullModelName.trim())}
            >
              <svg className="icon" viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" fill="none">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"></path>
              </svg>
              Pull Model ({selectedTagDetails ? selectedTagDetails.size : 'Download'})
            </button>
          ) : (
            <button 
              type="button" 
              className="btn btn-danger stop-pull-btn" 
              onClick={handleStopPull}
            >
              <svg className="icon" viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" fill="none">
                <rect x="6" y="6" width="12" height="12" rx="2" strokeWidth="2" fill="currentColor"></rect>
              </svg>
              Stop / Cancel Process
            </button>
          )}
        </div>

        {/* Live Streaming Progress Container */}
        {(isPulling || pullProgress > 0 || pullStatus) && (
          <div className="live-progress-container">
            <div className="progress-info-row">
              <div className="progress-status">
                {isPulling && <span className="spinner-tiny"></span>}
                <span className="status-text">{pullStatus || 'Processing...'}</span>
              </div>
              <div className="progress-metrics">
                {totalBytes > 0 && (
                  <span className="bytes-text">
                    {formatBytes(completedBytes)} / {formatBytes(totalBytes)}
                  </span>
                )}
                <span className="pct-badge">{pullProgress}%</span>
              </div>
            </div>

            <div className="progress-track">
              <div 
                className={`progress-fill ${pullSuccess ? 'fill-success' : isPulling ? 'fill-anim' : ''}`}
                style={{ width: `${pullProgress}%` }}
              ></div>
            </div>

            {pullError && (
              <div className="pull-error-msg">
                <span>⚠️ {pullError}</span>
              </div>
            )}

            {pullSuccess && (
              <div className="pull-success-msg">
                <span>✅ Model pulled successfully and ready to use!</span>
              </div>
            )}
          </div>
        )}
      </div>

      <style dangerouslySetInnerHTML={{__html: `
        .model-settings-screen {
          padding: 2rem;
          max-width: 860px;
          margin: 0 auto;
        }
        .error-banner {
          background-color: rgba(239, 68, 68, 0.1);
          color: #ef4444;
          padding: 1rem;
          border-radius: 8px;
          margin-bottom: 1.5rem;
          border: 1px solid rgba(239, 68, 68, 0.2);
        }
        .settings-section {
          background-color: var(--surface-light);
          border: 1px solid var(--border-light);
          border-radius: 12px;
          padding: 1.5rem;
          margin-bottom: 2rem;
        }
        .section-desc {
          color: var(--text-muted);
          font-size: 0.9rem;
          margin-top: 0.25rem;
          margin-bottom: 1.5rem;
        }
        .role-assignments-grid {
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }
        .role-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0.75rem 1rem;
          background-color: var(--surface);
          border-radius: 8px;
          border: 1px solid var(--border);
        }
        .role-label {
          font-weight: 500;
          color: var(--text);
          flex: 1;
        }
        .role-select {
          flex: 2;
          padding: 0.6rem 0.75rem;
          border-radius: 6px;
          border: 1px solid var(--border);
          background-color: var(--surface-light);
          color: var(--text);
          outline: none;
          font-size: 0.95rem;
        }
        .installed-models-list {
          list-style: none;
          padding: 0;
          margin: 0;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }
        .installed-model-item {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0.75rem 1rem;
          background-color: var(--surface);
          border-radius: 8px;
          border: 1px solid var(--border);
        }
        .model-name {
          font-weight: 500;
          font-family: monospace;
          color: var(--text);
        }
        .btn-danger {
          background-color: rgba(239, 68, 68, 0.15);
          color: #ef4444;
          border: 1px solid rgba(239, 68, 68, 0.3);
          padding: 0.5rem 0.75rem;
          border-radius: 6px;
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          font-weight: 500;
          transition: all 0.2s;
        }
        .btn-danger:hover {
          background-color: rgba(239, 68, 68, 0.25);
          border-color: #ef4444;
        }
        .btn-secondary {
          background-color: var(--surface);
          color: var(--text);
          border: 1px solid var(--border);
          padding: 0.75rem 1.25rem;
          border-radius: 8px;
          cursor: pointer;
          font-weight: 500;
          transition: all 0.2s;
        }
        .btn-secondary:hover:not(:disabled) {
          background-color: var(--border-light);
        }
        .btn-secondary:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        /* Search Bar */
        .model-search-bar {
          display: flex;
          gap: 0.75rem;
          margin-bottom: 1rem;
        }
        .search-input-wrapper {
          flex: 1;
          position: relative;
          display: flex;
          align-items: center;
        }
        .search-icon {
          position: absolute;
          left: 1rem;
          color: var(--text-muted);
          pointer-events: none;
        }
        .model-input {
          width: 100%;
          padding: 0.75rem 1rem 0.75rem 2.6rem;
          border-radius: 8px;
          border: 1px solid var(--border);
          background-color: var(--surface);
          color: var(--text);
          font-size: 0.95rem;
        }
        .model-input:focus {
          border-color: var(--primary, #3b82f6);
          outline: none;
        }
        .input-spinner {
          position: absolute;
          right: 1rem;
          width: 1rem;
          height: 1rem;
          border: 2px solid rgba(255, 255, 255, 0.2);
          border-top-color: var(--primary, #3b82f6);
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }

        /* Availability Status */
        .availability-status-container {
          margin-bottom: 1.25rem;
        }
        .status-pill {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.4rem 0.85rem;
          border-radius: 20px;
          font-size: 0.88rem;
        }
        .status-checking {
          background-color: rgba(59, 130, 246, 0.12);
          color: #60a5fa;
          border: 1px solid rgba(59, 130, 246, 0.25);
        }
        .status-available {
          background-color: rgba(16, 185, 129, 0.12);
          color: #34d399;
          border: 1px solid rgba(16, 185, 129, 0.25);
        }
        .status-not-available {
          background-color: rgba(239, 68, 68, 0.12);
          color: #f87171;
          border: 1px solid rgba(239, 68, 68, 0.25);
        }
        .pill-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }
        .pill-dot.green {
          background-color: #10b981;
          box-shadow: 0 0 6px #10b981;
        }
        .pill-dot.red {
          background-color: #ef4444;
        }

        /* Quant Panel */
        .quant-selection-panel {
          background-color: var(--surface);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 1.25rem;
          margin-bottom: 1.5rem;
        }
        .quant-panel-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 0.75rem;
          margin-bottom: 1rem;
        }
        .quant-panel-header h4 {
          margin: 0;
          font-size: 0.95rem;
          font-weight: 600;
        }
        .filter-chips {
          display: flex;
          gap: 0.5rem;
          flex-wrap: wrap;
        }
        .chip {
          background-color: var(--surface-light);
          border: 1px solid var(--border);
          color: var(--text-muted);
          padding: 0.25rem 0.65rem;
          border-radius: 6px;
          font-size: 0.8rem;
          cursor: pointer;
          transition: all 0.2s;
        }
        .chip:hover {
          color: var(--text);
          border-color: var(--border-light);
        }
        .chip.active {
          background-color: rgba(59, 130, 246, 0.15);
          color: #60a5fa;
          border-color: rgba(59, 130, 246, 0.4);
          font-weight: 600;
        }
        .tag-dropdown {
          width: 100%;
          background-color: var(--surface-light);
          padding: 0.75rem 1rem;
          font-family: monospace;
          font-size: 0.92rem;
        }
        .selected-summary-card {
          display: flex;
          align-items: center;
          justify-content: space-between;
          background-color: var(--surface-light);
          border: 1px solid var(--border-light);
          border-radius: 8px;
          padding: 0.85rem 1.2rem;
          margin-top: 1rem;
          gap: 1rem;
        }
        .summary-col {
          display: flex;
          flex-direction: column;
          gap: 0.2rem;
        }
        .summary-label {
          font-size: 0.75rem;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .summary-val {
          font-size: 0.95rem;
          color: var(--text);
        }
        .mono-highlight {
          font-family: monospace;
          color: #60a5fa;
        }
        .summary-badge {
          display: inline-block;
          background: rgba(59, 130, 246, 0.15);
          color: #93c5fd;
          padding: 0.15rem 0.5rem;
          border-radius: 4px;
          font-size: 0.82rem;
          font-weight: 600;
        }

        /* Action Buttons */
        .pull-action-area {
          display: flex;
          gap: 1rem;
          margin-bottom: 1.5rem;
        }
        .start-pull-btn {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.75rem 1.5rem;
          font-weight: 600;
          font-size: 0.95rem;
          background-color: #3b82f6;
          color: #fff;
          border: none;
          border-radius: 8px;
          cursor: pointer;
          transition: background-color 0.2s, transform 0.1s;
        }
        .start-pull-btn:hover:not(:disabled) {
          background-color: #2563eb;
        }
        .start-pull-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .stop-pull-btn {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.75rem 1.5rem;
          font-weight: 600;
          font-size: 0.95rem;
          background-color: #dc2626;
          color: #ffffff;
          border: none;
          border-radius: 8px;
          cursor: pointer;
          box-shadow: 0 0 12px rgba(220, 38, 38, 0.4);
          transition: background-color 0.2s;
        }
        .stop-pull-btn:hover {
          background-color: #b91c1c;
        }

        /* Live Progress Bar */
        .live-progress-container {
          background-color: var(--surface);
          border: 1px solid var(--border);
          border-radius: 10px;
          padding: 1.25rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }
        .progress-info-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 0.9rem;
        }
        .progress-status {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          color: var(--text);
          font-family: monospace;
        }
        .progress-metrics {
          display: flex;
          align-items: center;
          gap: 0.75rem;
        }
        .bytes-text {
          color: var(--text-muted);
          font-size: 0.85rem;
          font-family: monospace;
        }
        .pct-badge {
          background-color: rgba(59, 130, 246, 0.15);
          color: #60a5fa;
          padding: 0.2rem 0.5rem;
          border-radius: 4px;
          font-weight: 700;
          font-family: monospace;
        }
        .progress-track {
          width: 100%;
          height: 10px;
          background-color: var(--surface-light);
          border-radius: 5px;
          overflow: hidden;
          position: relative;
        }
        .progress-fill {
          height: 100%;
          background: linear-gradient(90deg, #3b82f6, #60a5fa);
          border-radius: 5px;
          transition: width 0.3s ease;
        }
        .fill-anim {
          box-shadow: 0 0 10px rgba(59, 130, 246, 0.5);
        }
        .fill-success {
          background: linear-gradient(90deg, #10b981, #34d399) !important;
        }
        .pull-error-msg {
          color: #f87171;
          font-size: 0.88rem;
          padding-top: 0.25rem;
        }
        .pull-success-msg {
          color: #34d399;
          font-size: 0.88rem;
          font-weight: 500;
          padding-top: 0.25rem;
        }

        .spinner-tiny {
          display: inline-block;
          width: 0.85rem;
          height: 0.85rem;
          border: 2px solid rgba(255, 255, 255, 0.2);
          border-radius: 50%;
          border-top-color: #60a5fa;
          animation: spin 0.8s linear infinite;
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}} />
    </div>
  );
}

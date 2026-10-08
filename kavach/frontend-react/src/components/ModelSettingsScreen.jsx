import React, { useState, useEffect, useRef, useMemo } from 'react';
import { API_BASE } from '../config';
import SovereignSelect from './SovereignSelect';

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

let _cachedRegistry = null;
let _cachedInstalledModels = null;

export default function ModelSettingsScreen() {
  const [registry, setRegistry] = useState(() => _cachedRegistry || {});
  const [installedModels, setInstalledModels] = useState(() => _cachedInstalledModels || []);
  const [loading, setLoading] = useState(() => !_cachedRegistry);
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

  // Model deletion modal states
  const [modelToDelete, setModelToDelete] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  // Active dropdown open tracking for flawless z-index stacking
  const [openRole, setOpenRole] = useState(null);
  const [isVariantOpen, setIsVariantOpen] = useState(false);

  const abortControllerRef = useRef(null);

  // Close modal on ESC key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && modelToDelete && !isDeleting) {
        setModelToDelete(null);
        setDeleteError(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [modelToDelete, isDeleting]);

  // Compute if model pending deletion is assigned to any roles
  const assignedRolesForDelete = useMemo(() => {
    if (!modelToDelete || !registry) return [];
    return Object.entries(registry)
      .filter(([_, m]) => m === modelToDelete)
      .map(([role]) => role);
  }, [modelToDelete, registry]);

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

  const fetchModels = async (forceSpinner = false) => {
    try {
      if (forceSpinner || !_cachedRegistry) {
        setLoading(true);
      }
      setError(null);
      const res = await fetch(`${API_BASE}/models`);
      if (!res.ok) throw new Error('Failed to fetch models');
      const data = await res.json();
      _cachedRegistry = data.registry || {};
      _cachedInstalledModels = data.installed || [];
      setRegistry(_cachedRegistry);
      setInstalledModels(_cachedInstalledModels);
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

  const promptDeleteModel = (modelName) => {
    setModelToDelete(modelName);
    setDeleteError(null);
  };

  const handleConfirmDelete = async () => {
    if (!modelToDelete || isDeleting) return;
    try {
      setIsDeleting(true);
      setDeleteError(null);
      const res = await fetch(`${API_BASE}/models/${encodeURIComponent(modelToDelete)}`, {
        method: 'DELETE'
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to delete model');
      }
      await fetchModels();
      setModelToDelete(null);
    } catch (err) {
      setDeleteError(err.message);
    } finally {
      setIsDeleting(false);
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
          {roles.map(role => {
            const roleOpts = [
              ...(registry[role] && !installedModels.includes(registry[role])
                ? [{ value: registry[role], label: `${registry[role]} (Not Installed)` }]
                : []),
              ...installedModels.map(m => ({ value: m, label: m })),
            ];
            const isThisRoleOpen = openRole === role;
            return (
              <div
                className={`role-row ${isThisRoleOpen ? 'has-open-select' : ''}`}
                key={role}
                style={{
                  position: 'relative',
                  zIndex: isThisRoleOpen ? 200 : 1,
                }}
              >
                <div className="role-label">{role.charAt(0).toUpperCase() + role.slice(1)}</div>
                <SovereignSelect 
                  value={registry[role] || ''}
                  onChange={(e) => handleAssign(role, e.target.value)}
                  onOpenChange={(isOpen) => setOpenRole(isOpen ? role : null)}
                  options={roleOpts}
                  placeholder="Select a model..."
                  align="center"
                  ariaLabel={`Model assignment for ${role}`}
                />
              </div>
            );
          })}
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
                  type="button"
                  className="btn btn-sm btn-danger" 
                  onClick={() => promptDeleteModel(m)}
                  title="Delete Model"
                >
                  <svg className="icon" viewBox="0 0 24 24" width="16" height="16" stroke="currentColor" fill="none">
                    <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"></path>
                  </svg>
                  <span>Delete</span>
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

            <div className="quant-selector-row" style={{ position: 'relative', zIndex: isVariantOpen ? 150 : 10 }}>
              <SovereignSelect 
                value={selectedTag}
                onChange={(e) => setSelectedTag(e.target.value)}
                onOpenChange={(isOpen) => setIsVariantOpen(isOpen)}
                options={filteredTags.map((t) => ({
                  value: t.full_name,
                  label: `${t.tag} • [${t.quantization}] • ${t.size}`,
                }))}
                disabled={isPulling}
                placeholder="Select a variant..."
                ariaLabel="Select model variant"
              />
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

      {/* In-App Model Deletion Confirmation Modal */}
      {modelToDelete && (
        <div
          className="confirm-overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget && !isDeleting) {
              setModelToDelete(null);
              setDeleteError(null);
            }
          }}
        >
          <div className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-modal-title">
            <div className="confirm-header">
              <div className="confirm-icon-box">
                <svg viewBox="0 0 24 24" style={{ width: '22px', height: '22px', stroke: 'currentColor', fill: 'none', strokeWidth: '2' }}>
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                  <line x1="10" y1="11" x2="10" y2="17" />
                  <line x1="14" y1="11" x2="14" y2="17" />
                </svg>
              </div>
              <div className="confirm-title-area">
                <h3 className="confirm-title" id="confirm-modal-title">Delete Model</h3>
                <p className="confirm-desc">
                  Are you sure you want to delete <span className="confirm-file-badge">{modelToDelete}</span> from local Ollama storage?
                </p>
              </div>
            </div>

            {assignedRolesForDelete.length > 0 ? (
              <div className="confirm-warning-box" style={{ background: 'rgba(239, 68, 68, 0.1)', borderColor: 'rgba(239, 68, 68, 0.3)', color: '#ef4444' }}>
                <svg className="icon icon-sm" viewBox="0 0 24 24" style={{ width: '16px', height: '16px', stroke: 'currentColor', fill: 'none', flexShrink: 0 }}>
                  <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <line x1="12" y1="9" x2="12" y2="13" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <line x1="12" y1="17" x2="12.01" y2="17" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>Currently assigned to <strong>{assignedRolesForDelete.join(', ')}</strong>. Deleting will leave those task roles unassigned.</span>
              </div>
            ) : (
              <div className="confirm-warning-box">
                <svg className="icon icon-sm" viewBox="0 0 24 24" style={{ width: '16px', height: '16px', stroke: 'currentColor', fill: 'none', flexShrink: 0 }}>
                  <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <line x1="12" y1="9" x2="12" y2="13" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <line x1="12" y1="17" x2="12.01" y2="17" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span>This will permanently delete the model weights from disk and reclaim storage space.</span>
              </div>
            )}

            {deleteError && (
              <div style={{ color: '#ef4444', fontSize: '12.5px', padding: '8px 12px', background: 'rgba(239, 68, 68, 0.1)', borderRadius: '6px', border: '1px solid rgba(239, 68, 68, 0.25)' }}>
                {deleteError}
              </div>
            )}

            <div className="confirm-actions">
              <button
                type="button"
                className="confirm-btn-cancel"
                onClick={() => {
                  setModelToDelete(null);
                  setDeleteError(null);
                }}
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
                    <span className="spinner-micro" />
                    <span>Deleting…</span>
                  </>
                ) : (
                  'Delete Model'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      <style dangerouslySetInnerHTML={{__html: `
        .model-settings-screen {
          padding: 28px 24px;
          max-width: 880px;
          margin: 0 auto;
        }
        .error-banner {
          background-color: rgba(239, 68, 68, 0.1);
          color: #ef4444;
          padding: 12px 18px;
          border-radius: var(--radius-pill);
          margin-bottom: 20px;
          border: 1px solid rgba(239, 68, 68, 0.25);
          font-size: 13.5px;
          font-weight: 500;
        }
        .settings-section {
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: var(--radius-lg);
          padding: 24px 26px;
          margin-bottom: 24px;
          box-shadow: var(--shadow-card);
        }
        .section-desc {
          color: var(--text-secondary);
          font-size: 13.5px;
          margin-top: 4px;
          margin-bottom: 20px;
          line-height: 1.5;
        }
        .role-assignments-grid {
          display: flex;
          flex-direction: column;
          gap: 12px;
          position: relative;
          overflow: visible !important;
        }
        .installed-models-list {
          list-style: none;
          padding: 0;
          margin: 0;
          display: flex;
          flex-direction: column;
          gap: 10px;
        }
        .installed-model-item {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 18px;
          background: var(--bg-page);
          border-radius: var(--radius);
          border: 1px solid var(--border);
          box-shadow: var(--shadow-soft);
          transition: transform 140ms var(--ease-spring), box-shadow 140ms var(--ease-spring);
        }
        .installed-model-item:hover {
          transform: translateY(-1px);
          box-shadow: var(--shadow-card);
        }
        .model-name {
          font-weight: 600;
          font-family: var(--font-mono, monospace);
          color: var(--text-primary);
          font-size: 13.5px;
        }
        .btn-danger {
          background: rgba(239, 68, 68, 0.12);
          color: #ef4444;
          border: 1px solid rgba(239, 68, 68, 0.3);
          padding: 7px 16px;
          border-radius: var(--radius-pill);
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          gap: 6px;
          font-weight: 600;
          font-size: 13px;
          transition: transform 140ms var(--ease-spring), box-shadow 140ms var(--ease-spring), background var(--ease);
        }
        .btn-danger:hover:not(:disabled) {
          background: rgba(239, 68, 68, 0.22);
          border-color: #ef4444;
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(239, 68, 68, 0.2);
        }
        .btn-danger:active:not(:disabled) {
          transform: scale(0.96) translateY(0.5px);
          transition-duration: 70ms;
        }
        .btn-secondary {
          background: var(--bg-card);
          color: var(--text-primary);
          border: 1px solid var(--border);
          padding: 9px 18px;
          border-radius: var(--radius-pill);
          cursor: pointer;
          font-weight: 500;
          font-size: 13px;
          transition: transform 140ms var(--ease-spring), box-shadow 140ms var(--ease-spring), background var(--ease);
        }
        .btn-secondary:hover:not(:disabled) {
          background: var(--bg-hover);
          transform: translateY(-1px);
          box-shadow: var(--shadow-soft);
        }
        .btn-secondary:active:not(:disabled) {
          transform: scale(0.96) translateY(0.5px);
          transition-duration: 70ms;
        }
        .btn-secondary:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        /* Search Bar */
        .model-search-bar {
          display: flex;
          gap: 12px;
          margin-bottom: 16px;
        }
        .search-input-wrapper {
          flex: 1;
          position: relative;
          display: flex;
          align-items: center;
        }
        .search-icon {
          position: absolute;
          left: 14px;
          color: var(--text-tertiary);
          pointer-events: none;
        }
        .model-input {
          width: 100%;
          padding: 10px 16px 10px 42px;
          border-radius: var(--radius-pill);
          border: 1px solid var(--border);
          background: var(--bg-page);
          color: var(--text-primary);
          font-size: 13.5px;
          outline: none;
          transition: border-color var(--ease), box-shadow var(--ease);
        }
        .model-input:focus {
          border-color: var(--kavach-accent);
          box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.15);
        }
        .input-spinner {
          position: absolute;
          right: 14px;
          width: 16px;
          height: 16px;
          border: 2px solid rgba(2, 132, 199, 0.25);
          border-top-color: var(--kavach-accent);
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }

        /* Availability Status */
        .availability-status-container {
          margin-bottom: 18px;
        }
        .status-pill {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 6px 14px;
          border-radius: var(--radius-pill);
          font-size: 13px;
          font-weight: 500;
        }
        .status-checking {
          background-color: rgba(2, 132, 199, 0.1);
          color: #0284c7;
          border: 1px solid rgba(2, 132, 199, 0.25);
        }
        .status-available {
          background-color: rgba(16, 185, 129, 0.1);
          color: #059669;
          border: 1px solid rgba(16, 185, 129, 0.25);
        }
        .status-not-available {
          background-color: rgba(239, 68, 68, 0.1);
          color: #dc2626;
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
          position: relative;
          z-index: 10;
          overflow: visible !important;
          background: var(--bg-page);
          border: 1px solid var(--border);
          border-radius: var(--radius-lg);
          padding: 18px 20px;
          margin-bottom: 20px;
        }
        .quant-selector-row {
          position: relative;
          width: 100%;
          max-width: 520px;
          overflow: visible !important;
        }
        .selected-summary-card {
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: var(--radius);
          padding: 12px 18px;
          margin-top: 14px;
          gap: 14px;
        }
        .summary-col {
          display: flex;
          flex-direction: column;
          gap: 3px;
        }
        .summary-label {
          font-size: 11px;
          color: var(--text-tertiary);
          text-transform: uppercase;
          letter-spacing: 0.5px;
          font-weight: 600;
        }
        .summary-val {
          font-size: 13.5px;
          color: var(--text-primary);
        }
        .mono-highlight {
          font-family: var(--font-mono, monospace);
          color: #0284c7;
          font-weight: 600;
        }
        .summary-badge {
          display: inline-block;
          background: rgba(2, 132, 199, 0.12);
          color: #0284c7;
          padding: 2px 10px;
          border-radius: var(--radius-pill);
          font-size: 12px;
          font-weight: 600;
        }

        /* Action Buttons */
        .pull-action-area {
          display: flex;
          gap: 12px;
          margin-bottom: 20px;
        }
        .start-pull-btn {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 10px 22px;
          font-weight: 600;
          font-size: 13.5px;
          background: linear-gradient(180deg, #0284c7 0%, #0369a1 100%);
          color: #fff;
          border: 1px solid rgba(2, 132, 199, 0.5);
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 2px 8px rgba(2, 132, 199, 0.3);
          border-radius: var(--radius-pill);
          cursor: pointer;
          transition: transform 160ms var(--ease-spring), box-shadow 160ms var(--ease-spring), background var(--ease);
        }
        .start-pull-btn:hover:not(:disabled) {
          background: linear-gradient(180deg, #0369a1 0%, #075985 100%);
          transform: translateY(-1.5px);
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3), 0 4px 14px rgba(2, 132, 199, 0.4);
        }
        .start-pull-btn:active:not(:disabled) {
          transform: scale(0.96) translateY(0.5px);
          transition-duration: 70ms;
        }
        .start-pull-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .stop-pull-btn {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          padding: 10px 22px;
          font-weight: 600;
          font-size: 13.5px;
          background: linear-gradient(180deg, #dc2626 0%, #b91c1c 100%);
          color: #ffffff;
          border: 1px solid rgba(220, 38, 38, 0.5);
          border-radius: var(--radius-pill);
          cursor: pointer;
          box-shadow: 0 2px 10px rgba(220, 38, 38, 0.35);
          transition: transform 160ms var(--ease-spring), box-shadow 160ms var(--ease-spring), background var(--ease);
        }
        .stop-pull-btn:hover {
          background: linear-gradient(180deg, #b91c1c 0%, #991b1b 100%);
          transform: translateY(-1.5px);
          box-shadow: 0 4px 14px rgba(220, 38, 38, 0.45);
        }
        .stop-pull-btn:active {
          transform: scale(0.96) translateY(0.5px);
          transition-duration: 70ms;
        }

        /* Live Progress Bar */
        .live-progress-container {
          background: var(--bg-card);
          border: 1px solid var(--border);
          border-radius: var(--radius-lg);
          padding: 20px 24px;
          display: flex;
          flex-direction: column;
          gap: 12px;
          box-shadow: var(--shadow-card);
        }
        .progress-info-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 13px;
        }
        .progress-status {
          display: flex;
          align-items: center;
          gap: 8px;
          color: var(--text-primary);
          font-family: var(--font-mono, monospace);
        }
        .progress-metrics {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .bytes-text {
          color: var(--text-secondary);
          font-size: 12px;
          font-family: var(--font-mono, monospace);
        }
        .pct-badge {
          background-color: rgba(2, 132, 199, 0.12);
          color: #0284c7;
          padding: 3px 10px;
          border-radius: var(--radius-pill);
          font-weight: 700;
          font-family: var(--font-mono, monospace);
          font-size: 12px;
        }
        .progress-track {
          width: 100%;
          height: 10px;
          background-color: var(--bg-hover);
          border-radius: var(--radius-pill);
          overflow: hidden;
          position: relative;
        }
        .progress-fill {
          height: 100%;
          background: linear-gradient(90deg, #0284c7, #38bdf8);
          border-radius: var(--radius-pill);
          transition: width 0.3s ease;
        }
        .fill-anim {
          box-shadow: 0 0 10px rgba(2, 132, 199, 0.5);
        }
        .fill-success {
          background: linear-gradient(90deg, #10b981, #34d399) !important;
        }
        .pull-error-msg {
          color: #ef4444;
          font-size: 13px;
          padding-top: 4px;
        }
        .pull-success-msg {
          color: #10b981;
          font-size: 13px;
          font-weight: 600;
          padding-top: 4px;
        }

        .spinner-tiny {
          display: inline-block;
          width: 14px;
          height: 14px;
          border: 2px solid rgba(2, 132, 199, 0.25);
          border-radius: 50%;
          border-top-color: #0284c7;
          animation: spin 0.8s linear infinite;
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        @media (max-width: 640px) {
          .model-settings-screen {
            padding: 1rem 0.75rem;
          }
          .settings-section {
            padding: 1rem;
            margin-bottom: 1.25rem;
          }
          .role-row {
            flex-direction: column;
            align-items: stretch;
            gap: 0.5rem;
          }
          .role-label {
            font-size: 0.9rem;
          }
          .role-select {
            width: 100%;
            font-size: 16px;
          }
          .model-search-bar {
            flex-direction: column;
          }
          .model-input {
            font-size: 16px;
          }
          .btn-secondary {
            width: 100%;
            justify-content: center;
          }
          .selected-summary-card {
            flex-direction: column;
            align-items: flex-start;
            gap: 0.75rem;
          }
          .pull-action-area {
            flex-direction: column;
          }
          .start-pull-btn, .stop-pull-btn {
            width: 100%;
            justify-content: center;
          }
          .progress-info-row {
            flex-direction: column;
            align-items: flex-start;
            gap: 0.4rem;
          }
        }
      `}} />
    </div>
  );
}

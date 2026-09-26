import React, { useState } from 'react';

export default function LockdownModal({ isOpen, onClose, onConfirmLockdown }) {
  const [isElevating, setIsElevating] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const handleConfirm = async () => {
    setIsElevating(true);
    setErrorMessage('');
    try {
      const res = await onConfirmLockdown();
      if (res && res.success) {
        onClose();
      } else {
        setErrorMessage(
          res?.error ||
          'Windows Administrator permission was not granted. Please click "Allow" when the Windows prompt appears.'
        );
      }
    } catch (err) {
      setErrorMessage(err.message || 'Failed to trigger elevation.');
    } finally {
      setIsElevating(false);
    }
  };

  const manualCommand = `powershell -ExecutionPolicy Bypass -File .\\scripts\\setup_firewall_permissions.ps1`;

  const copyCommand = () => {
    navigator.clipboard.writeText(manualCommand);
    setCopied(true);
    setTimeout(() => setCopied(false), 3000);
  };

  return (
    <div className="auth-overlay" onClick={(e) => e.target === e.currentTarget && !isElevating && onClose()}>
      <div className="auth-modal lockdown-modal" style={{ maxWidth: '480px' }}>
        <button
          className="auth-close-btn"
          onClick={onClose}
          disabled={isElevating}
          title="Close"
          aria-label="Close modal"
        >
          <svg className="icon" viewBox="0 0 24 24">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>

        <div className="auth-header">
          <div className="lockdown-modal-icon">
            <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: 'var(--accent, #00c9a7)' }}>
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <rect x="9" y="11" width="6" height="5" rx="1" />
              <path d="M10 11V9a2 2 0 0 1 4 0v2" />
            </svg>
          </div>
          <h2 className="auth-title" style={{ marginTop: '8px' }}>Security Permission Required</h2>
          <p className="auth-subtitle">
            Windows Defender Firewall Hardware Lockdown
          </p>
        </div>

        <div className="lockdown-modal-body" style={{ fontSize: '0.875rem', lineHeight: '1.5', color: '#475569', marginBottom: '20px' }}>
          <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px', marginBottom: '14px' }}>
            <div style={{ fontWeight: '600', color: '#0f172a', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', background: '#10b981' }}></span>
              What this action does:
            </div>
            <ul style={{ margin: '0', paddingLeft: '18px', color: '#334155' }}>
              <li>Flips Windows Defender Firewall outbound policy to <strong>Block</strong>.</li>
              <li>Instantly cuts off all external internet traffic to guarantee sovereign air-gap isolation.</li>
              <li>Localhost connections (KAVACH UI, FastAPI, Ollama LLM) remain 100% active.</li>
            </ul>
          </div>

          <p style={{ margin: '0 0 8px 0', color: '#334155' }}>
            Windows requires Administrator privileges to modify firewall rules. When you click <strong>Grant Permission</strong>, Windows will display a <strong>User Account Control (UAC)</strong> prompt on your screen asking:
          </p>
          <div style={{ background: '#f0f9ff', borderLeft: '3px solid #0284c7', padding: '8px 12px', borderRadius: '4px', color: '#0369a1', fontSize: '0.82rem', fontStyle: 'italic' }}>
            "Do you want to allow this app to make changes to your device?" → Please click <strong>Yes</strong>.
          </div>

          {errorMessage && (
            <div style={{ marginTop: '14px', padding: '10px 12px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', color: '#b91c1c', fontSize: '0.82rem' }}>
              <div style={{ fontWeight: '600', marginBottom: '4px' }}>Permission Notice</div>
              {errorMessage}
              <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid #fecaca' }}>
                <span>Or run this one-time command in an elevated PowerShell:</span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}>
                  <code style={{ background: '#0f172a', color: '#f8fafc', padding: '4px 6px', borderRadius: '4px', fontSize: '0.75rem', flex: 1, overflowX: 'auto' }}>
                    {manualCommand}
                  </code>
                  <button
                    type="button"
                    onClick={copyCommand}
                    style={{ background: '#334155', border: 'none', color: '#fff', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}
                  >
                    {copied ? 'Copied!' : 'Copy'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '12px' }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
            disabled={isElevating}
            style={{ padding: '8px 16px', borderRadius: '6px' }}
          >
            Cancel
          </button>

          <button
            type="button"
            className="auth-submit-btn"
            onClick={handleConfirm}
            disabled={isElevating}
            style={{ padding: '8px 18px', display: 'inline-flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}
          >
            {isElevating ? (
              <>
                <span className="auth-spinner"></span>
                <span>Waiting for Windows Prompt…</span>
              </>
            ) : (
              <>
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                </svg>
                <span>Grant Permission & Engage</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

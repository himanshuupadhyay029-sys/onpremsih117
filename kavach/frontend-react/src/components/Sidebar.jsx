import React from 'react';

export default function Sidebar({ activeScreen, onSelectScreen, isThinking, collapsed, onToggle }) {
  return (
    <aside className="sidebar" id="sidebar">
      <div className="sidebar-head">
        <div className={`wordmark ${isThinking ? 'is-thinking' : ''}`} id="wordmark">
          <svg className="icon" viewBox="0 0 24 24">
            <path d="M12 3l7 3v5.5c0 4.2-2.9 8.1-7 9.5-4.1-1.4-7-5.3-7-9.5V6l7-3z" />
          </svg>
          <span className="wordmark-text">KAVACH</span>
        </div>
        <button
          className="sidebar-collapse-btn"
          onClick={onToggle}
          title="Close sidebar"
          aria-label="Close sidebar"
        >
          <svg className="icon" viewBox="0 0 24 24">
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <path d="M9 4v16" />
          </svg>
        </button>
      </div>

      <nav className="nav">
        <button
          className={`nav-item ${activeScreen === 'task' ? 'is-active' : ''}`}
          onClick={() => onSelectScreen('task')}
        >
          <svg className="icon" viewBox="0 0 24 24">
            <path d="M12 5v14M5 12h14" />
          </svg>
          <span>New Task</span>
        </button>

        <button
          className={`nav-item ${activeScreen === 'vault' ? 'is-active' : ''}`}
          onClick={() => onSelectScreen('vault')}
        >
          <svg className="icon" viewBox="0 0 24 24">
            <path d="M4 7c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z" />
            <path d="M4 7v10c0 1.7 3.6 3 8 3s8-1.3 8-3V7" />
            <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
          </svg>
          <span>Knowledge Vault</span>
        </button>

        <button
          className={`nav-item ${activeScreen === 'audit' ? 'is-active' : ''}`}
          onClick={() => onSelectScreen('audit')}
        >
          <svg className="icon" viewBox="0 0 24 24">
            <path d="M8 6h12M8 12h12M8 18h12M3.5 6h.01M3.5 12h.01M3.5 18h.01" />
          </svg>
          <span>Audit Log</span>
        </button>
      </nav>

      <div className="sidebar-foot">Runs entirely on this machine.</div>
    </aside>
  );
}

import React, { useState, useEffect, useRef } from 'react';
import LockdownModal from './LockdownModal';

const IS_CLOUD = import.meta.env.VITE_CLOUD_DEPLOYMENT === 'true';

export default function TopBar({ sidebarCollapsed, onToggleSidebar }) {

  const [externalCount, setExternalCount] = useState(null);
  const [monitorStatus, setMonitorStatus] = useState('Connecting to monitor…');
  const [lockdownOn, setLockdownOn] = useState(false);
  const [isLocking, setIsLocking] = useState(false);
  const [lockdownModalOpen, setLockdownModalOpen] = useState(false);
  const [inlineNote, setInlineNote] = useState('');
  const noteTimerRef = useRef(null);

  const showNote = (msg) => {
    setInlineNote(msg);
    clearTimeout(noteTimerRef.current);
    noteTimerRef.current = setTimeout(() => {
      setInlineNote('');
    }, 9000);
  };

  // 1. Live WebSocket for connection sovereignty monitor
  useEffect(() => {
    let socket = null;
    let reconnectTimeout = null;

    const connect = () => {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      try {
        socket = new WebSocket(`${proto}//${host}/shield/monitor`);

        socket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            const count = data.external_count ?? 0;
            setExternalCount(count);
            setMonitorStatus(
              `Air-gapped · ${count} external connection${count === 1 ? '' : 's'}`
            );
          } catch {
            // ignore malformed frame
          }
        };

        socket.onclose = () => {
          setExternalCount(null);
          setMonitorStatus('Monitor disconnected');
          reconnectTimeout = setTimeout(connect, 3000);
        };
      } catch {
        reconnectTimeout = setTimeout(connect, 3000);
      }
    };

    connect();

    return () => {
      clearTimeout(reconnectTimeout);
      if (socket) socket.close();
    };
  }, []);

  // 2. Fetch initial firewall lockdown status
  useEffect(() => {
    fetch('/shield/status')
      .then((res) => res.json())
      .then((data) => {
        setLockdownOn(Boolean(data.firewall?.active));
      })
      .catch(() => {});
  }, []);

  // 3. Toggle firewall lockdown
  const handleToggleLockdown = async () => {
    if (lockdownOn) {
      // Unlocking
      setIsLocking(true);
      try {
        const response = await fetch('/shield/unlock?elevate=true', { method: 'POST' });
        const data = await response.json().catch(() => ({}));
        if (data.success !== false) {
          setLockdownOn(false);
          showNote('Hardware Firewall Lockdown disabled. Outbound internet restored.');
        } else {
          showNote(`Could not disable lockdown: ${data.error || response.statusText}`);
        }
      } catch (err) {
        showNote(`Could not reach shield endpoint: ${err.message}`);
      } finally {
        setIsLocking(false);
      }
      return;
    }

    // Attempt standard lockdown or check if elevation permission is needed
    setIsLocking(true);
    try {
      const response = await fetch('/shield/lockdown', { method: 'POST' });
      const data = await response.json().catch(() => ({}));
      if (data.requires_permission) {
        // Show interactive security permission modal
        setLockdownModalOpen(true);
      } else if (data.success || data.active) {
        setLockdownOn(true);
        showNote('Hardware Firewall Lockdown active.');
      } else {
        showNote(`Lockdown failed: ${data.error || response.statusText}`);
      }
    } catch (err) {
      showNote(`Could not reach shield endpoint: ${err.message}`);
    } finally {
      setIsLocking(false);
    }
  };

  // 4. Called when user clicks "Grant Permission & Engage" inside LockdownModal
  const handleConfirmElevate = async () => {
    try {
      const response = await fetch('/shield/lockdown?elevate=true', { method: 'POST' });
      const data = await response.json().catch(() => ({}));
      if (data.success && data.active) {
        setLockdownOn(true);
        showNote('Hardware Firewall Lockdown successfully engaged.');
        return { success: true };
      } else {
        return {
          success: false,
          error: data.error || 'Administrator elevation was not completed.',
        };
      }
    } catch (err) {
      return { success: false, error: err.message };
    }
  };

  const isSafe = externalCount === 0;
  const isAlert = externalCount !== null && externalCount > 0;

  return (
    <header className="topbar">
      <div className="topbar-left">
        {sidebarCollapsed && (
          <button
            className="sidebar-expand-btn"
            onClick={onToggleSidebar}
            title="Open sidebar"
            aria-label="Open sidebar"
          >
            <svg className="icon" viewBox="0 0 24 24">
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <path d="M9 4v16" />
            </svg>
          </button>
        )}
        {IS_CLOUD && (
          <div style={{
            background: 'rgba(251, 191, 36, 0.12)',
            border: '1px solid rgba(251, 191, 36, 0.4)',
            color: '#fbbf24',
            fontSize: '0.72rem',
            fontWeight: 500,
            padding: '3px 10px',
            borderRadius: '4px',
            letterSpacing: '0.03em',
            whiteSpace: 'nowrap',
          }}>
            ☁️ Cloud Demo — Sovereignty Shield &amp; Docker Sandbox are on-premises only
          </div>
        )}
      </div>


      <div className="topbar-right">
        <div className="sovereignty" title="Live connection monitor">
          <span
            className={`dot ${isSafe ? 'is-safe' : ''} ${isAlert ? 'is-alert' : ''}`}
            id="sov-dot"
          />
          <span id="sov-text">{monitorStatus}</span>
        </div>

        <button
          className={`lock-toggle ${lockdownOn ? 'is-on' : ''}`}
          onClick={handleToggleLockdown}
          disabled={isLocking}
          title={lockdownOn ? 'Lockdown active (Hardware Firewall Default-Deny)' : 'Click to enable Hardware Firewall Lockdown'}
        >
          <svg className="icon icon-sm" viewBox="0 0 24 24">
            <rect x="5" y="11" width="14" height="9" rx="2" />
            <path d="M8 11V8a4 4 0 118 0v3" />
          </svg>
          <span>
            {isLocking
              ? lockdownOn
                ? 'Unlocking…'
                : 'Checking…'
              : lockdownOn
              ? 'Lockdown on'
              : 'Lockdown off'}
          </span>
        </button>
      </div>

      {inlineNote && <div className="inline-note">{inlineNote}</div>}

      <LockdownModal
        isOpen={lockdownModalOpen}
        onClose={() => setLockdownModalOpen(false)}
        onConfirmLockdown={handleConfirmElevate}
      />
    </header>
  );
}

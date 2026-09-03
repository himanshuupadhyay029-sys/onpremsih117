import React, { useState, useEffect, useRef } from 'react';

export default function TopBar() {
  const [externalCount, setExternalCount] = useState(null);
  const [monitorStatus, setMonitorStatus] = useState('Connecting to monitor…');
  const [lockdownOn, setLockdownOn] = useState(false);
  const [isLocking, setIsLocking] = useState(false);
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
    const endpoint = lockdownOn ? '/shield/unlock' : '/shield/lockdown';
    setIsLocking(true);
    try {
      const response = await fetch(endpoint, { method: 'POST' });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const detail = String(body.detail || '');
        showNote(
          detail.includes('elevated') || response.status === 403
            ? 'Requires starting the server as Administrator.'
            : `Could not change lockdown: ${detail || response.statusText}`
        );
      } else {
        setLockdownOn(!lockdownOn);
      }
    } catch (err) {
      showNote(`Could not reach the shield endpoint: ${err.message}`);
    } finally {
      setIsLocking(false);
    }
  };

  const isSafe = externalCount === 0;
  const isAlert = externalCount !== null && externalCount > 0;

  return (
    <header className="topbar">
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
      >
        <svg className="icon icon-sm" viewBox="0 0 24 24">
          <rect x="5" y="11" width="14" height="9" rx="2" />
          <path d="M8 11V8a4 4 0 118 0v3" />
        </svg>
        <span>
          {isLocking
            ? lockdownOn
              ? 'Unlocking…'
              : 'Locking down…'
            : lockdownOn
            ? 'Lockdown on'
            : 'Lockdown off'}
        </span>
      </button>

      {inlineNote && <div className="inline-note">{inlineNote}</div>}
    </header>
  );
}

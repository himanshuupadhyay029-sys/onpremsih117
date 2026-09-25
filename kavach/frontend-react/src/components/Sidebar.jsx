import React, { useState } from 'react';

export default function Sidebar({
  activeScreen,
  onSelectScreen,
  isThinking,
  collapsed,
  onToggle,
  mobileNavOpen,
  onCloseMobile,
  user,
  onLogout,
  onShowAuth,
  chats,
  activeChatId,
  onNewChat,
  onSelectChat,
  runningChats,
}) {
  const [recentChatsOpen, setRecentChatsOpen] = useState(() => {
    return localStorage.getItem('kavach_recent_chats_open') !== '0';
  });

  const toggleRecentChats = (e) => {
    e.stopPropagation();
    setRecentChatsOpen((prev) => {
      const next = !prev;
      localStorage.setItem('kavach_recent_chats_open', next ? '1' : '0');
      return next;
    });
  };

  const hasAnyChatRunning = Boolean(
    runningChats && Object.values(runningChats).some((rc) => rc?.running)
  );

  const handleToggle = () => {
    if (onToggle) onToggle();
    if (onCloseMobile) onCloseMobile();
  };

  return (
    <aside className={`sidebar ${mobileNavOpen ? 'is-mobile-open' : ''}`} id="sidebar">
      <div className="sidebar-head">
        <div className={`wordmark ${isThinking ? 'is-thinking' : ''}`} id="wordmark">
          <svg className="icon" viewBox="0 0 24 24">
            <path d="M12 3l7 3v5.5c0 4.2-2.9 8.1-7 9.5-4.1-1.4-7-5.3-7-9.5V6l7-3z" />
          </svg>
          <span className="wordmark-text">KAVACH</span>
        </div>
        <button
          className="sidebar-collapse-btn"
          onClick={handleToggle}
          title="Close sidebar"
          aria-label="Close sidebar"
        >
          <svg className="icon" viewBox="0 0 24 24">
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <path d="M9 4v16" />
          </svg>
        </button>
      </div>

      {/* + New Chat button */}
      {user && (
        <button
          className="new-chat-btn"
          onClick={onNewChat}
          id="new-chat-btn"
          title="Start a new chat"
        >
          <svg className="icon" viewBox="0 0 24 24">
            <path d="M12 5v14M5 12h14" />
          </svg>
          <span>New Chat</span>
        </button>
      )}

      <nav className="nav">
        {/* Chat group with nested recent chats dropdown */}
        <div className="nav-chat-group">
          <div className={`nav-item nav-item-chat ${activeScreen === 'task' ? 'is-active' : ''}`}>
            <button
              type="button"
              className="nav-item-chat-main"
              onClick={() => onSelectScreen('task')}
              title="Open Chat"
            >
              <svg className="icon" viewBox="0 0 24 24">
                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
              </svg>
              <span>Chat</span>
              {hasAnyChatRunning && (
                <span className="nav-chat-running-beacon" title="Chat query is processing in the background" />
              )}
            </button>

            {user && (
              <button
                type="button"
                className={`chat-dropdown-toggle ${recentChatsOpen ? 'is-open' : ''}`}
                onClick={toggleRecentChats}
                title={recentChatsOpen ? 'Collapse recent chats' : 'Expand recent chats'}
                aria-label={recentChatsOpen ? 'Collapse recent chats' : 'Expand recent chats'}
              >
                <svg className="icon icon-xs chevron-icon" viewBox="0 0 24 24">
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </button>
            )}
          </div>

          {/* Collapsible Recent Chats Sub-list directly under Chat */}
          {user && recentChatsOpen && (
            <div className="chat-sublist" id="chat-sublist">
              {chats && chats.length > 0 ? (
                chats.map((chat) => {
                  const isRunning = Boolean(runningChats?.[chat.id]?.running);
                  const isSelected = activeScreen === 'task' && chat.id === activeChatId;

                  return (
                    <button
                      key={chat.id}
                      type="button"
                      className={`chat-subitem ${isSelected ? 'is-active' : ''} ${isRunning ? 'is-running' : ''}`}
                      onClick={() => onSelectChat(chat.id)}
                      title={chat.title + (isRunning ? ' (Processing…)' : '')}
                    >
                      {isRunning ? (
                        <span className="chat-running-indicator" title="Processing query…">
                          <svg className="icon icon-xs icon-spin" viewBox="0 0 24 24" fill="none">
                            <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" strokeDasharray="28" strokeLinecap="round" />
                          </svg>
                        </span>
                      ) : (
                        <svg className="icon icon-xs" viewBox="0 0 24 24">
                          <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
                        </svg>
                      )}
                      <span className="chat-subitem-title">{chat.title}</span>
                      {isRunning && (
                        <span className="chat-running-pulse-dot" title="Running…" />
                      )}
                    </button>
                  );
                })
              ) : (
                <div className="chat-subitem-empty">No recent chats</div>
              )}
            </div>
          )}
        </div>

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

        <button
          className={`nav-item ${activeScreen === 'models' ? 'is-active' : ''}`}
          onClick={() => onSelectScreen('models')}
        >
          <svg className="icon" viewBox="0 0 24 24">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
          <span>Model Settings</span>
        </button>
      </nav>

      {/* User profile block or sign-in prompt */}
      <div className="sidebar-foot">
        {user ? (
          <div className="user-profile" id="user-profile">
            <div className="user-avatar" id="user-avatar">
              {(user.name || user.email || '?').charAt(0).toUpperCase()}
            </div>
            <div className="user-info">
              <div className="user-name">{user.name}</div>
              <div className="user-email">{user.email}</div>
            </div>
            <button
              className="logout-btn"
              onClick={onLogout}
              title="Sign out"
              id="logout-btn"
            >
              <svg className="icon icon-sm" viewBox="0 0 24 24">
                <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
                <polyline points="16 17 21 12 16 7" />
                <line x1="21" y1="12" x2="9" y2="12" />
              </svg>
            </button>
          </div>
        ) : (
          <button
            className="sign-in-prompt"
            onClick={onShowAuth}
            id="sign-in-prompt"
          >
            <svg className="icon icon-sm" viewBox="0 0 24 24">
              <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
            <span>Sign in to save chats</span>
          </button>
        )}
      </div>
    </aside>
  );
}

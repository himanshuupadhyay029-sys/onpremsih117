import React from 'react';

export default function Sidebar({
  activeScreen,
  onSelectScreen,
  isThinking,
  collapsed,
  onToggle,
  user,
  onLogout,
  onShowAuth,
  chats,
  activeChatId,
  onNewChat,
  onSelectChat,
}) {
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
        <button
          className={`nav-item ${activeScreen === 'task' ? 'is-active' : ''}`}
          onClick={() => onSelectScreen('task')}
        >
          <svg className="icon" viewBox="0 0 24 24">
            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
          </svg>
          <span>Chat</span>
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

      {/* Chat History List (visible when on 'task' screen and user is logged in) */}
      {user && activeScreen === 'task' && chats && chats.length > 0 && (
        <div className="chat-history" id="chat-history">
          <div className="chat-history-label">Recent Chats</div>
          <div className="chat-history-list">
            {chats.map((chat) => (
              <button
                key={chat.id}
                className={`chat-history-item ${chat.id === activeChatId ? 'is-active' : ''}`}
                onClick={() => onSelectChat(chat.id)}
                title={chat.title}
              >
                <svg className="icon icon-sm" viewBox="0 0 24 24">
                  <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
                </svg>
                <span className="chat-history-title">{chat.title}</span>
              </button>
            ))}
          </div>
        </div>
      )}

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

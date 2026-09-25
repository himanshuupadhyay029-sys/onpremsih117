import React, { useState, useEffect } from 'react';

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
  onDeleteChat,
  runningChats,
}) {
  const [recentChatsOpen, setRecentChatsOpen] = useState(() => {
    return localStorage.getItem('kavach_recent_chats_open') !== '0';
  });

  const [chatToDelete, setChatToDelete] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  // Close confirmation modal on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && chatToDelete && !isDeleting) {
        setChatToDelete(null);
        setDeleteError(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [chatToDelete, isDeleting]);

  const toggleRecentChats = (e) => {
    e.stopPropagation();
    setRecentChatsOpen((prev) => {
      const next = !prev;
      localStorage.setItem('kavach_recent_chats_open', next ? '1' : '0');
      return next;
    });
  };

  const promptDeleteChat = (chat) => {
    setChatToDelete(chat);
    setDeleteError(null);
  };

  const handleConfirmDelete = async () => {
    if (!chatToDelete || isDeleting) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      if (onDeleteChat) {
        await onDeleteChat(chatToDelete.id);
      }
      setChatToDelete(null);
    } catch (err) {
      setDeleteError(err.message || 'Failed to delete chat');
    } finally {
      setIsDeleting(false);
    }
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
                    <div
                      key={chat.id}
                      className={`chat-subitem-row ${isSelected ? 'is-active' : ''} ${isRunning ? 'is-running' : ''}`}
                    >
                      <button
                        type="button"
                        className="chat-subitem-main"
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

                      <button
                        type="button"
                        className="chat-subitem-delete-btn"
                        onClick={(e) => {
                          e.stopPropagation();
                          promptDeleteChat(chat);
                        }}
                        title={`Delete chat "${chat.title}"`}
                        aria-label={`Delete chat "${chat.title}"`}
                      >
                        <svg viewBox="0 0 24 24">
                          <polyline points="3 6 5 6 21 6" />
                          <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                          <line x1="10" y1="11" x2="10" y2="17" />
                          <line x1="14" y1="11" x2="14" y2="17" />
                        </svg>
                      </button>
                    </div>
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
      {/* Delete Chat Confirmation Modal */}
      {chatToDelete && (
        <div
          className="confirm-overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget && !isDeleting) {
              setChatToDelete(null);
              setDeleteError(null);
            }
          }}
        >
          <div className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="delete-chat-modal-title">
            <div className="confirm-header">
              <div className="confirm-icon-box">
                <svg viewBox="0 0 24 24">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                  <line x1="10" y1="11" x2="10" y2="17" />
                  <line x1="14" y1="11" x2="14" y2="17" />
                </svg>
              </div>
              <div className="confirm-title-area">
                <h3 className="confirm-title" id="delete-chat-modal-title">Delete Chat</h3>
                <p className="confirm-desc">
                  Are you sure you want to delete <span className="confirm-file-badge">{chatToDelete.title}</span>?
                </p>
              </div>
            </div>

            <div className="confirm-warning-box">
              <svg className="icon icon-sm" viewBox="0 0 24 24" style={{ width: '16px', height: '16px', stroke: 'currentColor', fill: 'none', flexShrink: 0 }}>
                <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              <span>This will permanently delete this chat session and its full message history.</span>
            </div>

            {deleteError && (
              <div className="auth-error" style={{ margin: 0 }}>
                {deleteError}
              </div>
            )}

            <div className="confirm-actions">
              <button
                type="button"
                className="confirm-btn-cancel"
                onClick={() => {
                  setChatToDelete(null);
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
                    <span className="auth-spinner" style={{ width: '14px', height: '14px', borderWidth: '2px' }} />
                    <span>Deleting…</span>
                  </>
                ) : (
                  <>
                    <svg className="icon icon-sm" viewBox="0 0 24 24" style={{ width: '14px', height: '14px', stroke: 'currentColor', fill: 'none' }}>
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                    </svg>
                    <span>Delete Chat</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}

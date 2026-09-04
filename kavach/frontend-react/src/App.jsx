import React, { useState, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';
import NewTaskScreen from './components/NewTaskScreen';
import KnowledgeVaultScreen from './components/KnowledgeVaultScreen';
import AuditLogScreen from './components/AuditLogScreen';
import AuthModal from './components/AuthModal';

const API_BASE = '';

export default function App() {
  const [activeScreen, setActiveScreen] = useState('task');
  const [isThinking, setIsThinking] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem('kavach_sidebar_collapsed') === '1';
  });

  // Auth state
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);

  // Chat state with persistent selection
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatIdState] = useState(() => {
    return localStorage.getItem('kavach_active_chat_id') || null;
  });

  const setActiveChatId = useCallback((id) => {
    if (id) {
      localStorage.setItem('kavach_active_chat_id', id);
    } else {
      localStorage.removeItem('kavach_active_chat_id');
    }
    setActiveChatIdState(id);
  }, []);


  // Check existing session on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
        if (res.ok) {
          const data = await res.json();
          setUser(data);
        }
      } catch {
        // not authenticated
      } finally {
        setAuthChecked(true);
      }
    })();
  }, []);

  // Load chats when user is authenticated
  const loadChats = useCallback(async () => {
    if (!user) return;
    try {
      const res = await fetch(`${API_BASE}/chats`, { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        setChats(data);
      }
    } catch {
      // ignore
    }
  }, [user]);

  useEffect(() => {
    if (user) loadChats();
  }, [user, loadChats]);

  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('kavach_sidebar_collapsed', next ? '1' : '0');
      return next;
    });
  };

  const handleAuthSuccess = (userData) => {
    setUser(userData);
    setShowAuthModal(false);
  };

  const handleLogout = async () => {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      });
    } catch {
      // ignore
    }
    setUser(null);
    setChats([]);
    setActiveChatId(null);
  };

  const handleNewChat = () => {
    setActiveChatId(null);
    setActiveScreen('task');
  };

  const handleSelectChat = (chatId) => {
    setActiveChatId(chatId);
    setActiveScreen('task');
  };


  return (
    <div className={`app ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`} id="app-root">
      <Sidebar
        activeScreen={activeScreen}
        onSelectScreen={setActiveScreen}
        isThinking={isThinking}
        collapsed={sidebarCollapsed}
        onToggle={toggleSidebar}
        user={user}
        onLogout={handleLogout}
        onShowAuth={() => setShowAuthModal(true)}
        chats={chats}
        activeChatId={activeChatId}
        onNewChat={handleNewChat}
        onSelectChat={handleSelectChat}
      />

      <main className="main">
        <TopBar
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={toggleSidebar}
        />

        <div className="screens">
          {activeScreen === 'task' && (
            <NewTaskScreen
              setIsThinking={setIsThinking}
              user={user}
              activeChatId={activeChatId}
              setActiveChatId={setActiveChatId}
              onShowAuth={() => setShowAuthModal(true)}
              onChatsUpdated={loadChats}
            />
          )}
          {activeScreen === 'vault' && <KnowledgeVaultScreen />}
          {activeScreen === 'audit' && <AuditLogScreen />}
        </div>
      </main>

      {showAuthModal && (
        <AuthModal
          onClose={() => setShowAuthModal(false)}
          onAuthSuccess={handleAuthSuccess}
        />
      )}
    </div>
  );
}

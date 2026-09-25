import React, { useState, useEffect, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';
import NewTaskScreen from './components/NewTaskScreen';
import KnowledgeVaultScreen from './components/KnowledgeVaultScreen';
import AuditLogScreen from './components/AuditLogScreen';
import ModelSettingsScreen from './components/ModelSettingsScreen';
import AuthModal from './components/AuthModal';
import EvaluatorBriefingModal from './components/EvaluatorBriefingModal';
import ErrorBoundary from './components/ErrorBoundary';
import { API_BASE } from './config';


export default function App() {
  const [activeScreen, setActiveScreen] = useState('task');
  const [isThinking, setIsThinking] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem('kavach_sidebar_collapsed') === '1';
  });

  // SIH 117 Evaluator Architecture Notice State
  const [showBriefing, setShowBriefing] = useState(() => {
    return !sessionStorage.getItem('kavach_briefing_seen');
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

  const [mobileNavOpen, setMobileNavOpen] = useState(false);

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
    if (window.innerWidth <= 768) {
      setMobileNavOpen((prev) => !prev);
    } else {
      setSidebarCollapsed((prev) => {
        const next = !prev;
        localStorage.setItem('kavach_sidebar_collapsed', next ? '1' : '0');
        return next;
      });
    }
  };

  const closeMobileNav = useCallback(() => {
    setMobileNavOpen(false);
  }, []);

  const handleSelectScreen = (screen) => {
    setActiveScreen(screen);
    closeMobileNav();
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
    closeMobileNav();
  };

  const handleNewChat = () => {
    setActiveChatId(null);
    setActiveScreen('task');
    closeMobileNav();
  };

  const handleSelectChat = (chatId) => {
    setActiveChatId(chatId);
    setActiveScreen('task');
    closeMobileNav();
  };


  return (
    <div className={`app ${sidebarCollapsed ? 'sidebar-collapsed' : ''} ${mobileNavOpen ? 'mobile-nav-open' : ''}`} id="app-root">
      {/* Mobile Drawer Backdrop Scrim */}
      {mobileNavOpen && (
        <div
          className="sidebar-backdrop"
          onClick={closeMobileNav}
          aria-label="Close navigation drawer"
        />
      )}

      <Sidebar
        activeScreen={activeScreen}
        onSelectScreen={handleSelectScreen}
        isThinking={isThinking}
        collapsed={sidebarCollapsed}
        onToggle={toggleSidebar}
        mobileNavOpen={mobileNavOpen}
        onCloseMobile={closeMobileNav}
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
          mobileNavOpen={mobileNavOpen}
          onOpenBriefing={() => setShowBriefing(true)}
        />

        <div className={`screens ${activeScreen === 'task' ? 'screens-chat' : ''}`}>
          <ErrorBoundary>
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
            {activeScreen === 'vault' && (
              <KnowledgeVaultScreen
                user={user}
                onShowAuth={() => setShowAuthModal(true)}
              />
            )}
            {activeScreen === 'audit' && (
              <AuditLogScreen
                user={user}
                onShowAuth={() => setShowAuthModal(true)}
              />
            )}
            {activeScreen === 'models' && <ModelSettingsScreen />}
          </ErrorBoundary>
        </div>
      </main>

      {showAuthModal && (
        <AuthModal
          onClose={() => setShowAuthModal(false)}
          onAuthSuccess={handleAuthSuccess}
        />
      )}

      {/* SIH 117 Evaluator Architecture Briefing Gate */}
      <EvaluatorBriefingModal
        isOpen={showBriefing}
        onClose={() => setShowBriefing(false)}
        isFirstVisit={!sessionStorage.getItem('kavach_briefing_seen')}
      />
    </div>
  );
}

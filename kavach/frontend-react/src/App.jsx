import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';
import NewTaskScreen from './components/NewTaskScreen';
import KnowledgeVaultScreen from './components/KnowledgeVaultScreen';
import AuditLogScreen from './components/AuditLogScreen';

export default function App() {
  const [activeScreen, setActiveScreen] = useState('task');
  const [isThinking, setIsThinking] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    return localStorage.getItem('kavach_sidebar_collapsed') === '1';
  });

  const toggleSidebar = () => {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem('kavach_sidebar_collapsed', next ? '1' : '0');
      return next;
    });
  };

  return (
    <div className={`app ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`} id="app-root">
      <Sidebar
        activeScreen={activeScreen}
        onSelectScreen={setActiveScreen}
        isThinking={isThinking}
        collapsed={sidebarCollapsed}
        onToggle={toggleSidebar}
      />

      <main className="main">
        <TopBar
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={toggleSidebar}
        />

        <div className="screens">
          {activeScreen === 'task' && (
            <NewTaskScreen setIsThinking={setIsThinking} />
          )}
          {activeScreen === 'vault' && <KnowledgeVaultScreen />}
          {activeScreen === 'audit' && <AuditLogScreen />}
        </div>
      </main>
    </div>
  );
}

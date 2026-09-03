import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';
import NewTaskScreen from './components/NewTaskScreen';
import KnowledgeVaultScreen from './components/KnowledgeVaultScreen';
import AuditLogScreen from './components/AuditLogScreen';

export default function App() {
  const [activeScreen, setActiveScreen] = useState('task');
  const [isThinking, setIsThinking] = useState(false);

  return (
    <div className="app">
      <Sidebar
        activeScreen={activeScreen}
        onSelectScreen={setActiveScreen}
        isThinking={isThinking}
      />

      <main className="main">
        <TopBar />

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

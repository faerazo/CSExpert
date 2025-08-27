
import React, { useEffect } from 'react';
import MainLayout from '@/components/layout/MainLayout';
import { ChatInterface } from '@/components/chat/ChatInterface';
import { useChat } from '@/hooks/use-chat';
import { useNavigate, useParams } from 'react-router-dom';

const Index = () => {
  const navigate = useNavigate();
  const { sessionId: urlSessionId } = useParams<{ sessionId?: string }>();
  
  const {
    messages,
    isLoading,
    isSystemLoading,
    systemStatus,
    isSystemReady,
    systemDocumentCount,
    hasSystemError,
    sendMessage,
    editMessage,
    clearConversation,
    refetchSystemStatus,
    switchToSession,
    deleteSession,
    updateSessionTitle,
    sessionId,
    currentSession,
    sessions,
  } = useChat({ sessionId: urlSessionId });
  
  // Update URL when session changes
  useEffect(() => {
    if (sessionId && !urlSessionId) {
      // If we have a session but no URL param, update the URL
      navigate(`/chat/${sessionId}`, { replace: true });
    } else if (!sessionId && urlSessionId) {
      // If URL has session but we don't have it loaded, the hook will handle it
      // Just need to handle invalid session IDs
      const sessionExists = sessions.some(s => s.id === urlSessionId);
      if (sessions.length > 0 && !sessionExists) {
        // Session not found, redirect to home
        navigate('/', { replace: true });
      }
    }
  }, [sessionId, urlSessionId, navigate, sessions]);
  
  // Handle session selection with navigation
  const handleSessionSelect = (newSessionId: string) => {
    navigate(`/chat/${newSessionId}`);
    switchToSession(newSessionId);
  };
  
  // Handle new chat with navigation
  const handleNewChat = () => {
    navigate('/');
    clearConversation();
  };

  return (
    <MainLayout
      sessions={sessions}
      currentSessionId={sessionId}
      onSessionSelect={handleSessionSelect}
      onNewChat={handleNewChat}
      onDeleteSession={deleteSession}
      onRenameSession={updateSessionTitle}
    >
      <div className="flex flex-col h-full">
        <ChatInterface
          messages={messages}
          isLoading={isLoading}
          isSystemLoading={isSystemLoading}
          systemStatus={systemStatus}
          isSystemReady={isSystemReady}
          systemDocumentCount={systemDocumentCount}
          hasSystemError={hasSystemError}
          sendMessage={sendMessage}
          editMessage={editMessage}
          onNewChat={handleNewChat}
          refetchSystemStatus={refetchSystemStatus}
        />
      </div>
    </MainLayout>
  );
};

export default Index;

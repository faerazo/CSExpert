import React, { useRef, useEffect } from 'react';
import { ChatMessage, Message } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { Button } from '@/components/ui/button';
import { RefreshCw, AlertCircle, CheckCircle, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SystemStatus } from '@/lib/api';

interface ChatInterfaceProps {
  messages: Message[];
  isLoading: boolean;
  isSystemLoading: boolean;
  systemStatus?: SystemStatus;
  isSystemReady: boolean;
  systemDocumentCount: number;
  hasSystemError: boolean;
  sendMessage: (message: string) => void;
  onNewChat: () => void;
  refetchSystemStatus: () => void;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  messages,
  isLoading,
  isSystemLoading,
  systemStatus,
  isSystemReady,
  systemDocumentCount,
  hasSystemError,
  sendMessage,
  onNewChat,
  refetchSystemStatus,
}) => {
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // Scroll to the bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);
  
  const handleCitationClick = (citation: any) => {
    console.log('Citation clicked:', citation);
    // TODO: Implement document viewer or more info modal
  };

  // System status indicator
  const getStatusColor = () => {
    if (hasSystemError) return 'text-red-600';
    if (isSystemReady) return 'text-green-600';
    return 'text-yellow-600';
  };

  const getStatusText = () => {
    if (isSystemLoading) return 'Checking system status...';
    if (hasSystemError) return 'System error - some features may not work';
    if (isSystemReady) return `Ready - ${systemDocumentCount} documents loaded`;
    return systemStatus?.status || 'Unknown status';
  };
  
  return (
    <div className="flex flex-col h-full">
      {/* Header with system status */}
      <div className="p-4 border-b border-brand-medium">
        <div className="flex items-start justify-between">
          {/* Left side: Title and Status */}
          <div className="flex flex-col">
            <h1 className="text-xl font-bold text-brand-primary">CSExpert Chat</h1>
            
            {/* System status bar */}
            <div className="mt-2 flex items-center gap-2">
              {hasSystemError ? (
                <AlertCircle className="h-4 w-4 text-red-600" />
              ) : isSystemReady ? (
                <CheckCircle className="h-4 w-4 text-green-600" />
              ) : (
                <RefreshCw className="h-4 w-4 text-yellow-600 animate-spin" />
              )}
              <span className={cn("text-sm", getStatusColor())}>
                {getStatusText()}
              </span>
            </div>
          </div>
          
          {/* Right side: New Chat button (vertically centered) */}
          <div className="flex items-center">
            <Button
              onClick={onNewChat}
              className="bg-brand-primary hover:bg-brand-primary/90 text-white"
              size="sm"
              disabled={isLoading}
            >
              <Plus className="h-4 w-4 mr-2" />
              New Chat
            </Button>
          </div>
        </div>
      </div>
      
      {/* Messages area */}
      <div className="flex-1 p-4 space-y-4 overflow-y-auto bg-gray-50">
        {messages.map((message) => (
          <ChatMessage
            key={message.id}
            message={message}
            onCitationClick={handleCitationClick}
          />
        ))}
        
        {/* Show thinking indicator */}
        {isLoading && (
          <div className="flex items-center space-x-2 p-4 rounded-lg max-w-3xl chat-message-ai">
            <div className="text-sm font-medium">CSExpert is thinking</div>
            <div className="flex space-x-1">
              <div className="h-2 w-2 rounded-full bg-brand-secondary animate-pulse"></div>
              <div className="h-2 w-2 rounded-full bg-brand-secondary animate-pulse" style={{ animationDelay: '0.2s' }}></div>
              <div className="h-2 w-2 rounded-full bg-brand-secondary animate-pulse" style={{ animationDelay: '0.4s' }}></div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>
      
      {/* Input area */}
      <ChatInput
        onSendMessage={sendMessage}
        disabled={isLoading || !isSystemReady}
        placeholder={
          !isSystemReady 
            ? "System is loading..." 
            : "Ask about Computer Science courses and programs..."
        }
      />
    </div>
  );
};

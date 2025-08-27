import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { ChatHistory } from '@/components/chat/ChatHistory';
import { ChatSession } from '@/lib/chat-storage';

interface SidebarProps {
  sessions?: ChatSession[];
  currentSessionId?: string;
  onSessionSelect?: (sessionId: string) => void;
  onNewChat?: () => void;
  onDeleteSession?: (sessionId: string) => void;
  onRenameSession?: (sessionId: string, newTitle: string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  sessions = [],
  currentSessionId,
  onSessionSelect,
  onNewChat,
  onDeleteSession,
  onRenameSession,
}) => {
  const navigate = useNavigate();
  const location = useLocation();
  
  // Define navigation links
  const navigation = [
    { name: 'Chat', path: '/' },
  ];

  const isActive = (path: string) => {
    if (path === '/') {
      return location.pathname === '/' || location.pathname.startsWith('/chat/');
    }
    return location.pathname.startsWith(path);
  };
  
  return (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="p-4 border-b border-brand-medium">
        <div className="flex flex-col items-center">
          <img
            src="https://media.licdn.com/dms/image/v2/D4E0BAQEGltszpDpx3w/company-logo_200_200/company-logo_200_200/0/1665142883299/university_of_gothenburg_logo?e=2147483647&v=beta&t=NNyVbo6ITZdNXlFypJA6AVp3wtgY5dtO4hjNx3JM6oU"
            alt="CSExpert Logo"
            className="h-24 w-24 object-contain"
          />
          <span className="mt-3 text-xl font-bold text-brand-primary">CSExpert</span>
          <div className="text-xs text-brand-secondary mt-1 text-center">
            Course questions? I have answers!
          </div>
        </div>
      </div>
      
      {/* Show chat history or navigation based on current page */}
      {(location.pathname === '/' || location.pathname.startsWith('/chat/')) && onSessionSelect ? (
        <div className="flex-1 overflow-hidden">
          <div className="px-4 py-2 border-b border-brand-medium">
            <h3 className="text-sm font-medium text-gray-700">Chat History</h3>
          </div>
          <ChatHistory
            sessions={sessions}
            currentSessionId={currentSessionId}
            onSessionSelect={onSessionSelect}
            onNewChat={onNewChat || (() => {})}
            onDeleteSession={onDeleteSession || (() => {})}
            onRenameSession={onRenameSession || (() => {})}
          />
        </div>
      ) : (
        /* Navigation links for non-chat pages */
        <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
          {navigation.map((item) => (
            <a
              key={item.name}
              onClick={() => navigate(item.path)}
              className={cn(
                isActive(item.path)
                  ? 'bg-brand-light text-brand-primary font-medium'
                  : 'text-gray-600 hover:bg-brand-light hover:text-brand-primary',
                'group flex items-center px-3 py-2 text-base rounded-md cursor-pointer transition-colors'
              )}
            >
              {item.name}
            </a>
          ))}
        </nav>
      )}
    </div>
  );
};

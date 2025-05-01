
import React from 'react';
import { cn } from '@/lib/utils';

export interface Citation {
  id: string;
  title: string;
  page: number;
}

export interface Message {
  id: string;
  content: string;
  sender: 'user' | 'ai';
  timestamp: Date;
  citations?: Citation[];
}

interface ChatMessageProps {
  message: Message;
  onCitationClick?: (citation: Citation) => void;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  message,
  onCitationClick
}) => {
  const isUser = message.sender === 'user';
  
  return (
    <div className={cn(
      "p-4 rounded-lg max-w-3xl",
      isUser ? "ml-auto chat-message-user" : "mr-auto chat-message-ai"
    )}>
      <div className="flex flex-col">
        <div className="text-sm font-medium mb-1">
          {isUser ? 'You' : 'CSExpert'}
        </div>
        <div className="text-base">{message.content}</div>
        
        {/* Citations */}
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="mt-2 space-y-1">
            <div className="text-xs font-medium text-gray-500">Sources:</div>
            <div className="flex flex-wrap gap-1">
              {message.citations.map((citation) => (
                <button
                  key={citation.id}
                  onClick={() => onCitationClick?.(citation)}
                  className="inline-flex items-center px-2 py-1 rounded-full bg-brand-light text-xs hover:bg-brand-medium transition-colors"
                >
                  {citation.title} (p.{citation.page})
                </button>
              ))}
            </div>
          </div>
        )}
        
        {/* Timestamp */}
        <div className="text-xs text-gray-400 mt-1">
          {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  );
};

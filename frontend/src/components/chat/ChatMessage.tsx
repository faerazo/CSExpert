import React from 'react';
import { cn } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownRendererProps {
  content: string;
}

const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content }) => {
  // Error boundary and null check
  if (!content) {
    return <div className="markdown-content">No content</div>;
  }

  try {
    return (
      <div className="markdown-content prose prose-sm max-w-none">
        <ReactMarkdown 
          remarkPlugins={[remarkGfm]}
          components={{
            // Custom link renderer to open in new tab
            a: ({ node, href, children }) => (
              <a 
                href={href}
                target="_blank" 
                rel="noopener noreferrer"
                className="text-blue-800 hover:text-brand-accent underline transition-colors duration-200 font-medium"
              >
                {children}
              </a>
            ),
            // Custom code styling
            code: ({ node, inline, className, children, ...props }) => {
              const match = /language-(\w+)/.exec(className || '');
              return !inline ? (
                <pre className="bg-gray-900 text-gray-100 rounded-lg p-4 overflow-x-auto my-4 shadow-lg border border-gray-800">
                  <code className={`${className} text-sm leading-relaxed`} {...props}>
                    {children}
                  </code>
                </pre>
              ) : (
                <code className="bg-gray-100 text-red-600 px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
                  {children}
                </code>
              );
            },
            // Custom paragraph spacing with better line height
            p: ({ node, ...props }) => (
              <p className="mb-4 last:mb-0 leading-relaxed text-gray-800" {...props} />
            ),
            // Custom list styling with better spacing
            ul: ({ node, ...props }) => (
              <ul className="list-disc pl-6 mb-4 space-y-2 marker:text-gray-400" {...props} />
            ),
            ol: ({ node, ...props }) => (
              <ol className="list-decimal pl-6 mb-4 space-y-2 marker:text-gray-400" {...props} />
            ),
            li: ({ node, ...props }) => (
              <li className="leading-relaxed" {...props} />
            ),
            // Custom heading styling with better hierarchy
            h1: ({ node, ...props }) => (
              <h1 className="text-2xl font-bold mb-4 mt-6 first:mt-0 text-brand-primary border-b border-gray-200 pb-2" {...props} />
            ),
            h2: ({ node, ...props }) => (
              <h2 className="text-xl font-bold mb-3 mt-5 first:mt-0 text-brand-primary" {...props} />
            ),
            h3: ({ node, ...props }) => (
              <h3 className="text-lg font-semibold mb-2 mt-4 first:mt-0 text-brand-secondary" {...props} />
            ),
            h4: ({ node, ...props }) => (
              <h4 className="text-base font-semibold mb-2 mt-3 first:mt-0 text-gray-800" {...props} />
            ),
            // Enhanced blockquote styling
            blockquote: ({ node, ...props }) => (
              <blockquote className="border-l-4 border-brand-primary bg-gray-50 pl-4 pr-4 py-3 my-4 italic text-gray-700 rounded-r-md" {...props} />
            ),
            // Table styling for better readability
            table: ({ node, ...props }) => (
              <div className="overflow-x-auto my-4">
                <table className="min-w-full border-collapse border border-gray-300 rounded-lg overflow-hidden shadow-sm" {...props} />
              </div>
            ),
            thead: ({ node, ...props }) => (
              <thead className="bg-gray-100" {...props} />
            ),
            th: ({ node, ...props }) => (
              <th className="border border-gray-300 px-4 py-2 text-left font-semibold text-gray-800" {...props} />
            ),
            td: ({ node, ...props }) => (
              <td className="border border-gray-300 px-4 py-2 text-gray-700" {...props} />
            ),
            // Horizontal rule styling
            hr: ({ node, ...props }) => (
              <hr className="my-6 border-t-2 border-gray-200" {...props} />
            ),
            // Handle course codes and strong text
            strong: ({ node, children, ...props }) => {
              const text = String(children);
              // Check if it's a course code pattern
              if (/^[A-Z]{2,4}\d{3}[A-Z]?$/.test(text)) {
                return (
                  <span className="inline-flex items-center px-2 py-0.5 rounded text-sm font-semibold bg-brand-light text-brand-primary border border-brand-medium" {...props}>
                    {children}
                  </span>
                );
              }
              return <strong className="font-semibold text-gray-900" {...props}>{children}</strong>;
            },
            // Emphasis styling
            em: ({ node, ...props }) => (
              <em className="italic text-gray-700" {...props} />
            ),
            // Image styling
            img: ({ node, ...props }) => (
              <img className="rounded-lg shadow-md my-4 max-w-full h-auto" {...props} />
            ),
          }}
        >
          {content}
        </ReactMarkdown>
      </div>
    );
  } catch (error) {
    console.error('Error rendering markdown:', error);
    // Fallback to simple text if react-markdown fails
    return <div className="markdown-content whitespace-pre-wrap">{content}</div>;
  }
};

export interface Citation {
  id: string;
  title: string;
  page: number;
  metadata?: any; // Additional metadata from backend
}

export interface Message {
  id: string;
  content: string;
  sender: 'user' | 'ai';
  timestamp: Date;
  citations?: Citation[];
  metadata?: {
    contentType?: string;
    documentsRetrieved?: number;
  };
  isError?: boolean;
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
      "p-4 rounded-lg max-w-4xl", // Increased max-width for better markdown display
      isUser ? "ml-auto chat-message-user" : "mr-auto chat-message-ai",
      message.isError && "border-red-200 bg-red-50"
    )}>
      <div className="flex flex-col">
        <div className="flex items-center justify-between mb-2">
          <div className="text-sm font-medium">
            {isUser ? 'You' : 'CSExpert'}
          </div>
          {message.metadata?.contentType && (
            <div className="text-xs text-gray-500 capitalize">
              {message.metadata.contentType}
            </div>
          )}
        </div>
        
        <div className={cn(
          "text-base",
          message.isError && "text-red-700"
        )}>
          {isUser ? (
            // User messages: plain text
            <div className="whitespace-pre-wrap">{message.content}</div>
          ) : (
            // AI messages: markdown rendering
            <MarkdownRenderer content={message.content} />
          )}
        </div>
        
        {/* Citations */}
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="mt-3 space-y-2">
            <div className="text-xs font-medium text-gray-500">Sources:</div>
            <div className="flex flex-wrap gap-2">
              {message.citations.map((citation) => (
                <button
                  key={citation.id}
                  onClick={() => onCitationClick?.(citation)}
                  className="inline-flex items-center px-3 py-1 rounded-full bg-brand-light text-xs hover:bg-brand-medium transition-colors border border-brand-medium/30"
                  title={citation.metadata ? 
                    `${citation.metadata.course_code} - ${citation.metadata.section}` : 
                    citation.title
                  }
                >
                  {citation.title}
                </button>
              ))}
            </div>
          </div>
        )}
        
        {/* Metadata info */}
        {!isUser && message.metadata?.documentsRetrieved && (
          <div className="text-xs text-gray-400 mt-2">
            Retrieved {message.metadata.documentsRetrieved} documents
          </div>
        )}
        
        {/* Timestamp */}
        <div className="text-xs text-gray-400 mt-2">
          {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  );
};

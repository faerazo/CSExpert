import React from 'react';
import { cn } from '@/lib/utils';

// Professional markdown renderer using standard HTML elements
const SimpleMarkdownRenderer: React.FC<{ content: string }> = ({ content }) => {
  const parseMarkdown = (text: string) => {
    // Escape HTML for security
    text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    
    // Code blocks (before other formatting)
    text = text.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
    
    // Inline code
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Headers
    text = text.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    text = text.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    text = text.replace(/^# (.+)$/gm, '<h1>$1</h1>');
    
    // Bold and italic
    text = text.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/__([^_\n]+)__/g, '<strong>$1</strong>');
    text = text.replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, '<em>$1</em>');
    text = text.replace(/(?<!_)_([^_\n]+)_(?!_)/g, '<em>$1</em>');
    
    // Links
    text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    
    // Course codes
    text = text.replace(/\b([A-Z]{2,4}\d{3})\b/g, '<span class="course-code">$1</span>');
    
    // Blockquotes
    text = text.replace(/^>\s+(.+)$/gm, '<blockquote>$1</blockquote>');
    
    // Horizontal rules
    text = text.replace(/^---+$/gm, '<hr>');
    text = text.replace(/^\*\*\*+$/gm, '<hr>');
    
    // Strikethrough
    text = text.replace(/~~([^~]+)~~/g, '<del>$1</del>');
    
    // Lists - improved parsing
    const lines = text.split('\n');
    const processedLines = [];
    let inUnorderedList = false;
    let inOrderedList = false;
    
    for (const line of lines) {
      const unorderedMatch = line.match(/^(\s*)([*+-])\s+(.+)$/);
      const orderedMatch = line.match(/^(\s*)(\d+)\.\s+(.+)$/);
      
      if (unorderedMatch) {
        const [, indent, , content] = unorderedMatch;
        const indentLevel = Math.floor(indent.length / 2);
        
        if (inOrderedList) {
          processedLines.push('</ol>');
          inOrderedList = false;
        }
        
        if (!inUnorderedList) {
          processedLines.push('<ul>');
          inUnorderedList = true;
        }
        
        processedLines.push(`<li>${content}</li>`);
        
      } else if (orderedMatch) {
        const [, , , content] = orderedMatch;
        
        if (inUnorderedList) {
          processedLines.push('</ul>');
          inUnorderedList = false;
        }
        
        if (!inOrderedList) {
          processedLines.push('<ol>');
          inOrderedList = true;
        }
        
        processedLines.push(`<li>${content}</li>`);
        
      } else {
        if (inUnorderedList) {
          processedLines.push('</ul>');
          inUnorderedList = false;
        }
        if (inOrderedList) {
          processedLines.push('</ol>');
          inOrderedList = false;
        }
        processedLines.push(line);
      }
    }
    
    // Close any remaining lists
    if (inUnorderedList) processedLines.push('</ul>');
    if (inOrderedList) processedLines.push('</ol>');
    
    text = processedLines.join('\n');
    
    // Paragraphs
    const paragraphs = text.split(/\n\s*\n/);
    const formattedParagraphs = paragraphs.map(para => {
      para = para.trim();
      if (!para) return '';
      
      // Skip if already wrapped in block elements
      if (para.match(/^<(h[1-6]|ul|ol|blockquote|hr|pre|div)/)) {
        return para;
      }
      
      // Convert line breaks to <br> and wrap in <p>
      const withBreaks = para.replace(/\n/g, '<br>');
      return `<p>${withBreaks}</p>`;
    }).filter(p => p);
    
    return formattedParagraphs.join('\n');
  };

  return (
    <div className="markdown-content">
      <div dangerouslySetInnerHTML={{ __html: parseMarkdown(content) }} />
    </div>
  );
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
            // AI messages: simple markdown rendering
            <SimpleMarkdownRenderer content={message.content} />
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

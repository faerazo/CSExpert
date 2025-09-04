import React, { useState } from 'react';
import { cn } from '@/lib/utils';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronDown, ChevronUp, FileText, Copy, Edit2, Check, X, User } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/hooks/use-toast';

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
            code: ({ node, className, children, ...props }: any) => {
              const match = /language-(\w+)/.exec(className || '');
              const inline = !match;
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
    topCourses?: string[];
  };
  isError?: boolean;
}

interface ChatMessageProps {
  message: Message;
  onCitationClick?: (citation: Citation) => void;
  onEditMessage?: (messageId: string, newContent: string) => void;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({
  message,
  onCitationClick,
  onEditMessage
}) => {
  const isUser = message.sender === 'user';
  const [showSources, setShowSources] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(message.content);
  const [showActions, setShowActions] = useState(false);
  const { toast } = useToast();
  
  // Build syllabus URL from course code (consistent pattern)
  const getSyllabusUrl = (courseCode: string) => {
    return `https://kursplaner.gu.se/pdf/kurs/en/${courseCode}`;
  };
  
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      toast({
        description: "Message copied to clipboard",
        duration: 2000,
      });
    } catch (error) {
      toast({
        variant: "destructive",
        description: "Failed to copy message",
        duration: 2000,
      });
    }
  };
  
  const handleEdit = () => {
    setIsEditing(true);
    setEditContent(message.content);
  };
  
  const handleSaveEdit = () => {
    if (editContent.trim() && editContent !== message.content && onEditMessage) {
      onEditMessage(message.id, editContent.trim());
      setIsEditing(false);
    } else {
      setIsEditing(false);
    }
  };
  
  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditContent(message.content);
  };
  
  return (
    <div 
      className={cn(
        "p-4 rounded-lg max-w-4xl group relative", // Added group and relative for hover effects
        isUser ? "ml-auto chat-message-user" : "mr-auto chat-message-ai",
        message.isError && "border-red-200 bg-red-50"
      )}
      onMouseEnter={() => !isUser && setShowActions(true)}
      onMouseLeave={() => !isUser && setShowActions(false)}
    >
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
            // User messages
            isEditing ? (
              <div className="space-y-2">
                <Textarea
                  value={editContent}
                  onChange={(e) => setEditContent(e.target.value)}
                  className="min-h-[60px] resize-none"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      handleSaveEdit();
                    }
                  }}
                />
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    onClick={handleSaveEdit}
                    disabled={!editContent.trim() || editContent === message.content}
                  >
                    <Check className="h-3.5 w-3.5 mr-1" />
                    Save
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={handleCancelEdit}
                  >
                    <X className="h-3.5 w-3.5 mr-1" />
                    Cancel
                  </Button>
                  <span className="text-xs text-gray-500">
                    Press Shift+Enter for a new line
                  </span>
                </div>
              </div>
            ) : (
              <div className="whitespace-pre-wrap">{message.content}</div>
            )
          ) : (
            // AI messages: markdown rendering
            <MarkdownRenderer content={message.content} />
          )}
        </div>
        
        {/* Sources section with copy button */}
        {!isUser && message.id !== 'welcome' && (
          <div className="mt-4 border-t border-gray-200 pt-3">
            <div className="flex items-center gap-2">
              {/* Copy button - always show first */}
              <Button
                size="sm"
                variant="ghost"
                className="h-6 w-6 p-0"
                onClick={handleCopy}
                title="Copy message"
              >
                <Copy className="h-3 w-3" />
              </Button>
              
              {/* Sources toggle button - only if citations exist */}
              {message.citations && message.citations.length > 0 && (
                <button
                  onClick={() => setShowSources(!showSources)}
                  className="flex items-center gap-2 hover:bg-gray-50 rounded-lg px-2 py-1 transition-all duration-200"
                >
                  <FileText className="h-3.5 w-3.5 text-gray-400" />
                  <span className="text-xs text-gray-600 font-medium flex items-center gap-1">
                    {message.citations.length} sources
                    {message.metadata?.documentsRetrieved && 
                      ` • ${message.metadata.documentsRetrieved} documents searched`
                    }
                  </span>
                  {showSources ? 
                    <ChevronUp className="h-3.5 w-3.5 text-gray-400" /> : 
                    <ChevronDown className="h-3.5 w-3.5 text-gray-400" />
                  }
                </button>
              )}
            </div>
            
            {/* Expandable sources content */}
            {showSources && (
              <div className="mt-3 space-y-2 pl-2 animate-in slide-in-from-top-2 duration-200">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {message.citations.map((citation) => {
                    const courseCode = citation.metadata?.course_code;
                    const hasCourseCode = courseCode && /^[A-Z]{2,4}\d{3}[A-Z]?$/.test(courseCode);
                    
                    return (
                      <div
                        key={citation.id}
                        className="flex items-start gap-2 p-3 rounded-lg bg-gray-50 hover:bg-gray-100 transition-all duration-200 hover:shadow-sm border border-gray-100"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="text-xs font-medium text-gray-700 truncate">
                            {citation.title}
                          </div>
                          {citation.metadata?.section_name && (
                            <div className="text-xs text-gray-500 truncate">
                              {citation.metadata.section_name}
                            </div>
                          )}
                        </div>
                        
                        {/* Syllabus link - only if we have a valid course code */}
                        {hasCourseCode && (
                          <a
                            href={getSyllabusUrl(courseCode)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="p-1.5 hover:bg-gray-200 rounded transition-all duration-200 hover:scale-110"
                            title={`View ${courseCode} syllabus (PDF)`}
                            onClick={(e) => e.stopPropagation()}
                          >
                            <FileText className="h-3 w-3 text-brand-primary" />
                          </a>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
        
        {/* Bottom section with timestamp and user actions */}
        <div className="flex items-center justify-between mt-2">
          <div className="text-xs text-gray-400">
            {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </div>
          
          {/* User message actions - bottom right */}
          {isUser && (
            <div className="flex items-center gap-1">
              <Button
                size="sm"
                variant="ghost"
                className="h-6 w-6 p-0"
                onClick={handleCopy}
                title="Copy message"
              >
                <Copy className="h-3 w-3" />
              </Button>
              {onEditMessage && !isEditing && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 w-6 p-0"
                  onClick={handleEdit}
                  title="Edit message"
                >
                  <Edit2 className="h-3 w-3" />
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

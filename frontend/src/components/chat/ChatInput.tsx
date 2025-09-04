import React, { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Send, Sparkles } from 'lucide-react';

interface ChatInputProps {
  onSendMessage: (message: string) => void;
  placeholder?: string;
  disabled?: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  onSendMessage,
  placeholder = "Ask about Computer Science courses and programs...",
  disabled = false
}) => {
  const [message, setMessage] = useState('');
  const [isExpanded, setIsExpanded] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  
  // Auto-resize textarea based on content
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      // Reset height to auto to get the correct scrollHeight
      textarea.style.height = 'auto';
      
      // Calculate new height (min 80px, max 200px)
      const newHeight = Math.min(Math.max(textarea.scrollHeight, 80), 200);
      textarea.style.height = `${newHeight}px`;
      
      // Update expanded state based on content
      setIsExpanded(newHeight > 80);
    }
  }, [message]);
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    if (message.trim() && !disabled) {
      onSendMessage(message.trim());
      setMessage('');
    }
  };
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
    // Shift+Enter will naturally add a new line (default textarea behavior)
  };
  
  return (
    <form onSubmit={handleSubmit} className="p-6 border-t border-brand-medium bg-white">
      <div className="space-y-3">
        <div className="flex items-end gap-3">
          <Textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            className="flex-1 min-h-[80px] max-h-[200px] resize-none focus:outline-none focus-visible:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 transition-colors duration-150 overflow-y-auto text-base leading-relaxed border border-gray-200 hover:border-gray-300 focus:border-gray-400 rounded-lg px-4 py-3 shadow-sm placeholder:text-gray-400 bg-white"
            maxLength={2000}
            style={{ height: '80px' }}
          />
          
          <Button 
            type="submit"
            disabled={!message.trim() || disabled}
            className={`px-4 bg-brand-primary hover:bg-brand-primary/85 text-white transition-all duration-150 focus:outline-none focus-visible:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 ${
              isExpanded ? 'h-12' : 'h-[80px]'
            } ${!message.trim() || disabled ? 'opacity-50 cursor-not-allowed' : 'hover:scale-[0.98] active:scale-[0.96]'}`}
          >
            <Send size={18} />
          </Button>
        </div>
        
        <div className="flex justify-between items-center">
          <div className="text-xs text-gray-500">
            {!disabled && "Press Shift+Enter for a new line"}
          </div>
          <div className={`text-xs transition-colors ${
            message.length > 1800 ? 'text-red-500' : 
            message.length > 1500 ? 'text-yellow-600' : 'text-gray-400'
          }`}>
            {message.length}/2000
          </div>
        </div>
      </div>
    </form>
  );
};

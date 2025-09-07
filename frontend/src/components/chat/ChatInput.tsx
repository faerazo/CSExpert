import React, { useState, useRef, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Send } from 'lucide-react';

interface ChatInputProps {
  onSendMessage: (message: string) => void;
  placeholder?: string;
  disabled?: boolean;
}

const PLACEHOLDER_EXAMPLES = [
  "Ask about Computer Science and Engineering courses and programs...",
  "What are the prerequisites for the advanced database course?",
  "What are the learning outcomes for the introduction to data science and AI course?",
  "Does DIT968 have an exam?",
  "What programs does GU offer?"
];

export const ChatInput: React.FC<ChatInputProps> = ({
  onSendMessage,
  placeholder,
  disabled = false
}) => {
  const [message, setMessage] = useState('');
  const [isExpanded, setIsExpanded] = useState(false);
  const [currentPlaceholderIndex, setCurrentPlaceholderIndex] = useState(0);
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
  
  // Cycle through placeholder examples
  useEffect(() => {
    let timeoutId: NodeJS.Timeout | null = null;
    
    if (!message) {
      // Only cycle placeholders when there's no user input
      const schedulePlaceholderChange = () => {
        let delay: number;
        if (currentPlaceholderIndex === 0) {
          // Wait longer on the default placeholder before showing examples
          delay = 15000;
        } else if (currentPlaceholderIndex === PLACEHOLDER_EXAMPLES.length - 1) {
          // Pause before cycling back to default
          delay = 4500;
        } else {
          // Normal delay between examples
          delay = 4000;
        }
        
        timeoutId = setTimeout(() => {
          setCurrentPlaceholderIndex((prevIndex) => {
            const nextIndex = (prevIndex + 1) % PLACEHOLDER_EXAMPLES.length;
            return nextIndex;
          });
        }, delay);
      };
      
      schedulePlaceholderChange();
      
      return () => {
        if (timeoutId) {
          clearTimeout(timeoutId);
        }
      };
    } else {
      // Reset to default when user types
      setCurrentPlaceholderIndex(0);
    }
  }, [message, currentPlaceholderIndex]);
  
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
  
  // Use the cycling placeholder examples
  const actualPlaceholder = PLACEHOLDER_EXAMPLES[currentPlaceholderIndex];
  
  return (
    <form onSubmit={handleSubmit} className="p-6 border-t border-brand-medium bg-white">
      <div className="space-y-3">
        <div className="flex items-end gap-3">
          <Textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={actualPlaceholder}
            disabled={disabled}
            className="flex-1 min-h-[80px] max-h-[200px] resize-none focus:outline-none focus-visible:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 transition-all duration-150 overflow-y-auto text-base leading-relaxed border border-gray-200 hover:border-gray-300 focus:border-gray-400 rounded-lg px-4 py-3 shadow-sm placeholder:text-gray-400 placeholder:transition-opacity placeholder:duration-500 bg-white"
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

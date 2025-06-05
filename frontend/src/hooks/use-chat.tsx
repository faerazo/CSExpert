import { useState, useEffect, useCallback } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { api, ChatResponse, SystemStatus, getErrorMessage } from '@/lib/api';
import { Message } from '@/components/chat/ChatMessage';
import { useToast } from '@/hooks/use-toast';

export interface UseChatOptions {
  sessionId?: string;
}

export const useChat = (options: UseChatOptions = {}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>(options.sessionId);
  const { toast } = useToast();

  // Initialize with welcome message
  useEffect(() => {
    const welcomeMessage: Message = {
      id: 'welcome',
      content: 'Hello! I am CSExpert, your assistant for Gothenburg University Computer Science and Engineering courses and programs. How can I help you today?',
      sender: 'ai',
      timestamp: new Date(),
    };
    setMessages([welcomeMessage]);
  }, []);

  // System status query
  const { 
    data: systemStatus, 
    isLoading: isSystemLoading,
    error: systemError,
    refetch: refetchSystemStatus
  } = useQuery<SystemStatus>({
    queryKey: ['systemStatus'],
    queryFn: api.getSystemStatus,
    refetchInterval: 30000, // Refetch every 30 seconds
    refetchOnWindowFocus: true,
  });

  // Chat mutation
  const chatMutation = useMutation({
    mutationFn: api.sendMessage,
    onSuccess: (response: ChatResponse) => {
      console.log('=== CHAT HOOK SUCCESS ===');
      console.log('Received response:', response);
      console.log('Processing response into message...');

      const aiMessage: Message = {
        id: Date.now().toString(),
        content: response.answer,
        sender: 'ai',
        timestamp: new Date(),
        citations: response.sources.map((source, index) => ({
          id: `source-${index}`,
          title: source.course_code ? 
            `${source.course_code} - ${source.course_title}` : 
            source.course_title,
          page: 1, // Backend doesn't provide page numbers, so we use 1
          metadata: source, // Store full source data
        })),
        metadata: {
          contentType: response.content_type,
          documentsRetrieved: response.num_documents_retrieved,
        }
      };

      console.log('Created AI message:', aiMessage);
      console.log('Message content length:', aiMessage.content?.length || 0);
      console.log('Message content preview:', aiMessage.content?.substring(0, 100) + '...');

      setMessages(prev => {
        console.log('Adding message to chat. Current messages:', prev.length);
        const newMessages = [...prev, aiMessage];
        console.log('New message count:', newMessages.length);
        return newMessages;
      });
      
      // Update session ID if provided
      if (response.session_id) {
        setSessionId(response.session_id);
        console.log('Updated session ID:', response.session_id);
      }

      console.log('=== END CHAT HOOK SUCCESS ===');
    },
    onError: (error) => {
      console.error('=== CHAT HOOK ERROR ===');
      console.error('Chat mutation error:', error);
      console.error('Error type:', error.constructor.name);

      const errorMessage: Message = {
        id: Date.now().toString(),
        content: `I apologize, but I encountered an error: ${getErrorMessage(error)}. Please try again or visit the official Gothenburg University website for more information.`,
        sender: 'ai',
        timestamp: new Date(),
        isError: true,
      };

      console.log('Created error message:', errorMessage);

      setMessages(prev => [...prev, errorMessage]);
      
      toast({
        variant: "destructive",
        title: "Error",
        description: getErrorMessage(error),
      });

      console.log('=== END CHAT HOOK ERROR ===');
    },
  });

  // Send message function
  const sendMessage = useCallback(async (message: string) => {
    const trimmedMessage = message.trim();
    if (!trimmedMessage) return;

    console.log('=== SEND MESSAGE START ===');
    console.log('User message:', trimmedMessage);
    console.log('Message length:', trimmedMessage.length);

    // Create user message
    const userMessage: Message = {
      id: Date.now().toString(),
      content: trimmedMessage,
      sender: 'user',
      timestamp: new Date(),
    };

    console.log('Created user message:', userMessage);

    // Add user message immediately
    setMessages(prev => {
      console.log('Adding user message. Current count:', prev.length);
      const newMessages = [...prev, userMessage];
      console.log('New count after user message:', newMessages.length);
      return newMessages;
    });

    // Send to API
    console.log('Triggering API mutation...');
    chatMutation.mutate({
      message: trimmedMessage,
      session_id: sessionId,
    });

    console.log('=== SEND MESSAGE END ===');
  }, [sessionId, chatMutation]);

  // Clear conversation
  const clearConversation = useCallback(() => {
    setMessages([{
      id: 'welcome',
      content: 'Hello! I am CSExpert, your assistant for Gothenburg University Computer Science and Engineering courses and programs. How can I help you today?',
      sender: 'ai',
      timestamp: new Date(),
    }]);
    setSessionId(undefined);
  }, []);

  // System status helpers
  const isSystemReady = systemStatus?.status === 'initialized';
  const systemDocumentCount = systemStatus?.total_documents || 0;
  const hasSystemError = !!systemError || systemStatus?.status === 'error';

  return {
    // Messages and state
    messages,
    isLoading: chatMutation.isPending,
    isSystemLoading,
    
    // System status
    systemStatus,
    isSystemReady,
    systemDocumentCount,
    hasSystemError,
    systemError,
    
    // Actions
    sendMessage,
    clearConversation,
    refetchSystemStatus,
    
    // Session
    sessionId,
  };
}; 
import { useState, useEffect, useCallback } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { api, ChatResponse, SystemStatus, getErrorMessage } from '@/lib/api';
import { Message } from '@/components/chat/ChatMessage';
import { useToast } from '@/hooks/use-toast';
import { chatStorage, ChatSession } from '@/lib/chat-storage';

export interface UseChatOptions {
  sessionId?: string;
}

export const useChat = (options: UseChatOptions = {}) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId, setSessionId] = useState<string | undefined>(options.sessionId);
  const [currentSession, setCurrentSession] = useState<ChatSession | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const { toast } = useToast();

  // Load sessions and initialize
  useEffect(() => {
    const loadedSessions = chatStorage.getSessions();
    setSessions(loadedSessions);

    // If sessionId is provided, load that session
    if (options.sessionId) {
      const session = chatStorage.getSession(options.sessionId);
      if (session) {
        setCurrentSession(session);
        setMessages(session.messages);
        setSessionId(session.id);
        chatStorage.setCurrentSession(session.id);
        return;
      }
    }

    // Initialize with just welcome message, no session created yet
    const welcomeMessage: Message = {
      id: 'welcome',
      content: 'Hello! I am CSExpert, your assistant for Gothenburg University Computer Science and Engineering courses and programs. How can I help you today?',
      sender: 'ai',
      timestamp: new Date(),
    };
    setMessages([welcomeMessage]);
    setCurrentSession(null);
    setSessionId(undefined);
  }, [options.sessionId]);

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

  // Chat mutation with context to handle session switching
  const chatMutation = useMutation({
    mutationFn: api.sendMessage,
    onMutate: async (variables) => {
      // Store the target session ID in context
      // This ensures responses go to the correct session even if user switches
      return { 
        targetSessionId: variables.session_id
      };
    },
    onSuccess: (response: ChatResponse, variables, context) => {
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
          topCourses: response.top_courses || [],
        }
      };

      // Get the target session ID from context (where the question was asked)
      const targetSessionId = context?.targetSessionId;
      
      if (targetSessionId) {
        // Always update storage for the correct session
        const targetSession = chatStorage.getSession(targetSessionId);
        if (targetSession) {
          // Add AI message to the correct session's messages
          const updatedMessages = [...targetSession.messages, aiMessage];
          chatStorage.updateSessionMessages(targetSessionId, updatedMessages);
          
          // Update sessions list to reflect changes
          const updatedSessions = chatStorage.getSessions();
          setSessions(updatedSessions);
          
          // Only update UI if we're still on the same session
          if (sessionId === targetSessionId) {
            setMessages(updatedMessages);
            
            // Update current session to reflect title change
            const updatedSession = updatedSessions.find(s => s.id === targetSessionId);
            if (updatedSession) {
              setCurrentSession(updatedSession);
            }
          } else {
            // User has switched sessions - show a toast notification
            toast({
              title: "Response received",
              description: `Answer added to chat: ${targetSession.title}`,
              duration: 3000,
            });
          }
        }
      } else {
        // Fallback to old behavior if no context
        setMessages(prev => {
          const newMessages = [...prev, aiMessage];
          if (sessionId) {
            chatStorage.updateSessionMessages(sessionId, newMessages);
          }
          return newMessages;
        });
      }
      
      // Update session ID if provided
      if (response.session_id) {
        setSessionId(response.session_id);
      }
    },
    onError: (error, variables, context) => {
      const errorMessage: Message = {
        id: Date.now().toString(),
        content: `I apologize, but I encountered an error: ${getErrorMessage(error)}. Please try again or visit the official Gothenburg University website for more information.`,
        sender: 'ai',
        timestamp: new Date(),
        isError: true,
      };

      // Get the target session ID from context (where the question was asked)
      const targetSessionId = context?.targetSessionId;
      
      if (targetSessionId) {
        // Always update storage for the correct session
        const targetSession = chatStorage.getSession(targetSessionId);
        if (targetSession) {
          // Add error message to the correct session's messages
          const updatedMessages = [...targetSession.messages, errorMessage];
          chatStorage.updateSessionMessages(targetSessionId, updatedMessages);
          
          // Update sessions list
          const updatedSessions = chatStorage.getSessions();
          setSessions(updatedSessions);
          
          // Only update UI if we're still on the same session
          if (sessionId === targetSessionId) {
            setMessages(updatedMessages);
            
            // Update current session
            const updatedSession = updatedSessions.find(s => s.id === targetSessionId);
            if (updatedSession) {
              setCurrentSession(updatedSession);
            }
          }
        }
      } else {
        // Fallback to old behavior if no context
        setMessages(prev => {
          const newMessages = [...prev, errorMessage];
          if (sessionId) {
            chatStorage.updateSessionMessages(sessionId, newMessages);
          }
          return newMessages;
        });
      }
      
      toast({
                variant: "destructive",
        title: "Error",
        description: getErrorMessage(error),
      });
    },
  });

  // Send message function
  const sendMessage = useCallback(async (message: string) => {
    const trimmedMessage = message.trim();
    if (!trimmedMessage) return;

    // Create session on first user message if needed
    let activeSessionId = sessionId;
    if (!sessionId) {
      const newSession = chatStorage.createSession();
      setCurrentSession(newSession);
      setSessionId(newSession.id);
      activeSessionId = newSession.id;
      
      // Update welcome message in the new session
      const welcomeMessage = messages.find(m => m.id === 'welcome');
      if (welcomeMessage) {
        chatStorage.updateSessionMessages(newSession.id, [welcomeMessage]);
      }
      
      // Update sessions list
      setSessions(chatStorage.getSessions());
    }

    // Create user message
    const userMessage: Message = {
      id: Date.now().toString(),
      content: trimmedMessage,
      sender: 'user',
      timestamp: new Date(),
    };

    // Add user message to the correct session immediately
    const sessionMessages = activeSessionId === sessionId ? messages : 
      (chatStorage.getSession(activeSessionId)?.messages || messages);
    
    const newMessagesWithUser = [...sessionMessages, userMessage];
    
    // Persist to storage for the correct session
    if (activeSessionId) {
      chatStorage.updateSessionMessages(activeSessionId, newMessagesWithUser);
      
      // Update sessions to reflect any title changes (happens on first user message)
      const updatedSessions = chatStorage.getSessions();
      setSessions(updatedSessions);
      
      // Only update UI if we're on this session
      if (activeSessionId === sessionId) {
        setMessages(newMessagesWithUser);
        
        // Update current session to reflect title change
        const updatedSession = updatedSessions.find(s => s.id === activeSessionId);
        if (updatedSession) {
          setCurrentSession(updatedSession);
        }
      }
    } else {
      // No session yet, just update local state
      setMessages(prev => [...prev, userMessage]);
    }

    // Prepare chat history for context (exclude welcome message AND current message)
    // Use the messages BEFORE the current message for history
    const chatHistory = sessionMessages
      .filter(m => m.id !== 'welcome')
      .map(m => {
        const historyMsg: any = {
          sender: m.sender,
          content: m.content,
        };
        
        // Include sources for AI messages to enable better context retrieval
        if (m.sender === 'ai' && m.citations && m.citations.length > 0) {
          historyMsg.sources = m.citations.map(c => c.metadata).filter(Boolean);
        }
        
        // Include top courses for better context tracking
        if (m.sender === 'ai' && m.metadata?.topCourses && m.metadata.topCourses.length > 0) {
          historyMsg.top_courses = m.metadata.topCourses;
        }
        
        return historyMsg;
      });
    
    // Send to API
    chatMutation.mutate({
      message: trimmedMessage,
      session_id: activeSessionId,
      chat_history: chatHistory,
    });
  }, [sessionId, messages, chatMutation, setSessions, setCurrentSession, setSessionId, setMessages]);

  // Edit message and resend
  const editMessage = useCallback(async (messageId: string, newContent: string) => {
    if (!sessionId || !currentSession) return;
    
    // Find the message index
    const messageIndex = messages.findIndex(m => m.id === messageId);
    if (messageIndex === -1) return;
    
    // Get all messages up to and including the edited one
    const messagesBeforeEdit = messages.slice(0, messageIndex);
    
    // Create the edited message
    const editedMessage: Message = {
      ...messages[messageIndex],
      content: newContent,
      timestamp: new Date(),
    };
    
    // Update messages: keep everything before the edited message, add the edited message
    const newMessages = [...messagesBeforeEdit, editedMessage];
    
    // Check if this is the first user message (excluding welcome message)
    const firstUserMessageIndex = messages.findIndex(m => m.sender === 'user' && m.id !== 'welcome');
    if (messageIndex === firstUserMessageIndex) {
      // Update the session title with the new content
      const newTitle = chatStorage.generateTitle(newContent);
      chatStorage.updateSessionTitle(sessionId, newTitle);
      
      // Update current session state
      setCurrentSession({ ...currentSession, title: newTitle });
      
      // Update sessions list
      setSessions(chatStorage.getSessions());
    }
    
    // Update UI and storage
    setMessages(newMessages);
    chatStorage.updateSessionMessages(sessionId, newMessages);
    
    // Prepare chat history for the API (exclude welcome message)
    const chatHistory = messagesBeforeEdit
      .filter(m => m.id !== 'welcome')
      .map(m => {
        const historyMsg: any = {
          sender: m.sender,
          content: m.content,
        };
        
        // Include sources for AI messages
        if (m.sender === 'ai' && m.citations && m.citations.length > 0) {
          historyMsg.sources = m.citations.map(c => c.metadata).filter(Boolean);
        }
        
        return historyMsg;
      });
    
    // Send the edited message to the API
    chatMutation.mutate({
      message: newContent,
      session_id: sessionId,
      chat_history: chatHistory,
    });
  }, [sessionId, currentSession, messages, chatMutation, setMessages, setCurrentSession, setSessions]);

  // Clear conversation (resets to initial state, no session)
  const clearConversation = useCallback(() => {
    const welcomeMessage: Message = {
      id: 'welcome',
      content: 'Hello! I am CSExpert, your assistant for Gothenburg University Computer Science and Engineering courses and programs. How can I help you today?',
      sender: 'ai',
      timestamp: new Date(),
    };
    
    setMessages([welcomeMessage]);
    setSessionId(undefined);
    setCurrentSession(null);
    
    // No need to reload sessions since we didn't create a new one
  }, []);
  
  // Switch to a different session
  const switchToSession = useCallback((targetSessionId: string) => {
    const session = chatStorage.getSession(targetSessionId);
    if (session) {
      setCurrentSession(session);
      setMessages(session.messages);
      setSessionId(session.id);
      chatStorage.setCurrentSession(session.id);
    }
  }, []);
  
  // Delete a session
  const deleteSession = useCallback((targetSessionId: string) => {
    chatStorage.deleteSession(targetSessionId);
    setSessions(chatStorage.getSessions());
    
    // If we deleted the current session, create a new one
    if (targetSessionId === sessionId) {
      clearConversation();
    }
  }, [sessionId, clearConversation]);
  
  // Update session title
  const updateSessionTitle = useCallback((targetSessionId: string, title: string) => {
    chatStorage.updateSessionTitle(targetSessionId, title);
    setSessions(chatStorage.getSessions());
    
    // Update current session if it's the one being renamed
    if (targetSessionId === sessionId && currentSession) {
      setCurrentSession({ ...currentSession, title });
    }
  }, [sessionId, currentSession]);

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
    editMessage,
    clearConversation,
    refetchSystemStatus,
    switchToSession,
    deleteSession,
    updateSessionTitle,
    
    // Session
    sessionId,
    currentSession,
    sessions,
  };
}; 
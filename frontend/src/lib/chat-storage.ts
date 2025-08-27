import { Message } from '@/components/chat/ChatMessage';

export interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  createdAt: Date;
  updatedAt: Date;
}

export interface ChatStorageData {
  sessions: ChatSession[];
  currentSessionId: string | null;
}

const STORAGE_KEY = 'csexpert_chat_history';
const MAX_SESSIONS = 50; // Limit to prevent localStorage from getting too large
const MAX_TITLE_LENGTH = 60;

export class ChatStorage {
  private static instance: ChatStorage;

  private constructor() {}

  static getInstance(): ChatStorage {
    if (!ChatStorage.instance) {
      ChatStorage.instance = new ChatStorage();
    }
    return ChatStorage.instance;
  }

  /**
   * Generate a unique session ID
   */
  generateSessionId(): string {
    return `chat_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
  }

  /**
   * Generate a title from the first user message
   */
  generateTitle(firstUserMessage: string): string {
    // Clean and truncate the message for title
    const cleaned = firstUserMessage
      .replace(/[\n\r]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    
    if (cleaned.length <= MAX_TITLE_LENGTH) {
      return cleaned;
    }
    
    // Truncate at word boundary
    const truncated = cleaned.substring(0, MAX_TITLE_LENGTH);
    const lastSpace = truncated.lastIndexOf(' ');
    
    return lastSpace > 40 
      ? truncated.substring(0, lastSpace) + '...'
      : truncated + '...';
  }
  
  /**
   * Generate a smart title based on the conversation context
   * This could be enhanced with AI summarization
   */
  generateSmartTitle(messages: Message[]): string {
    // Find the first user message
    const firstUserMessage = messages.find(m => m.sender === 'user');
    if (!firstUserMessage) {
      return 'New Chat';
    }
    
    // For now, use the simple title generation
    // In the future, this could use AI to generate a better summary
    return this.generateTitle(firstUserMessage.content);
  }

  /**
   * Get all data from localStorage
   */
  private getData(): ChatStorageData {
    try {
      const data = localStorage.getItem(STORAGE_KEY);
      if (!data) {
        return { sessions: [], currentSessionId: null };
      }
      
      const parsed = JSON.parse(data);
      
      // Convert date strings back to Date objects
      parsed.sessions = parsed.sessions.map((session: any) => ({
        ...session,
        createdAt: new Date(session.createdAt),
        updatedAt: new Date(session.updatedAt),
        messages: session.messages.map((msg: any) => ({
          ...msg,
          timestamp: new Date(msg.timestamp)
        }))
      }));
      
      return parsed;
    } catch (error) {
      return { sessions: [], currentSessionId: null };
    }
  }

  /**
   * Save data to localStorage
   */
  private saveData(data: ChatStorageData): void {
    try {
      // Limit number of sessions
      if (data.sessions.length > MAX_SESSIONS) {
        // Sort by updatedAt and keep only the most recent
        data.sessions.sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime());
        data.sessions = data.sessions.slice(0, MAX_SESSIONS);
      }
      
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch (error) {
      
      // If localStorage is full, try to clean up old sessions
      if (error instanceof DOMException && error.name === 'QuotaExceededError') {
        this.cleanupOldSessions();
        
        // Try again
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        } catch (retryError) {
          // Failed to save after cleanup
        }
      }
    }
  }

  /**
   * Create a new chat session
   */
  createSession(): ChatSession {
    const data = this.getData();
    
    const newSession: ChatSession = {
      id: this.generateSessionId(),
      title: 'New Chat',
      messages: [],
      createdAt: new Date(),
      updatedAt: new Date()
    };
    
    data.sessions.unshift(newSession); // Add to beginning
    data.currentSessionId = newSession.id;
    
    this.saveData(data);
    return newSession;
  }

  /**
   * Get all sessions
   */
  getSessions(): ChatSession[] {
    const data = this.getData();
    return data.sessions;
  }

  /**
   * Get current session
   */
  getCurrentSession(): ChatSession | null {
    const data = this.getData();
    if (!data.currentSessionId) return null;
    
    return data.sessions.find(s => s.id === data.currentSessionId) || null;
  }

  /**
   * Get session by ID
   */
  getSession(sessionId: string): ChatSession | null {
    const data = this.getData();
    return data.sessions.find(s => s.id === sessionId) || null;
  }

  /**
   * Set current session
   */
  setCurrentSession(sessionId: string): void {
    const data = this.getData();
    if (data.sessions.find(s => s.id === sessionId)) {
      data.currentSessionId = sessionId;
      this.saveData(data);
    }
  }

  /**
   * Update session messages
   */
  updateSessionMessages(sessionId: string, messages: Message[]): void {
    const data = this.getData();
    const sessionIndex = data.sessions.findIndex(s => s.id === sessionId);
    
    if (sessionIndex !== -1) {
      data.sessions[sessionIndex].messages = messages;
      data.sessions[sessionIndex].updatedAt = new Date();
      
      // Update title if it's still "New Chat" and we have a user message
      if (data.sessions[sessionIndex].title === 'New Chat') {
        const firstUserMessage = messages.find(m => m.sender === 'user');
        if (firstUserMessage) {
          data.sessions[sessionIndex].title = this.generateTitle(firstUserMessage.content);
        }
      }
      
      // Move to top of list (most recent)
      const session = data.sessions.splice(sessionIndex, 1)[0];
      data.sessions.unshift(session);
      
      this.saveData(data);
    }
  }

  /**
   * Update session title
   */
  updateSessionTitle(sessionId: string, title: string): void {
    const data = this.getData();
    const session = data.sessions.find(s => s.id === sessionId);
    
    if (session) {
      session.title = title;
      session.updatedAt = new Date();
      this.saveData(data);
    }
  }

  /**
   * Delete a session
   */
  deleteSession(sessionId: string): void {
    const data = this.getData();
    data.sessions = data.sessions.filter(s => s.id !== sessionId);
    
    // If we deleted the current session, clear it
    if (data.currentSessionId === sessionId) {
      data.currentSessionId = null;
    }
    
    this.saveData(data);
  }

  /**
   * Clear all sessions
   */
  clearAllSessions(): void {
    this.saveData({ sessions: [], currentSessionId: null });
  }

  /**
   * Clean up old sessions to free up space
   */
  private cleanupOldSessions(): void {
    const data = this.getData();
    
    // Keep only the 30 most recent sessions
    data.sessions.sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime());
    data.sessions = data.sessions.slice(0, 30);
    
    this.saveData(data);
  }

  /**
   * Export sessions as JSON
   */
  exportSessions(): string {
    const data = this.getData();
    return JSON.stringify(data, null, 2);
  }

  /**
   * Import sessions from JSON
   */
  importSessions(jsonData: string): boolean {
    try {
      const imported = JSON.parse(jsonData);
      
      // Validate structure
      if (!imported.sessions || !Array.isArray(imported.sessions)) {
        throw new Error('Invalid data structure');
      }
      
      // Merge with existing data
      const currentData = this.getData();
      
      // Add imported sessions, avoiding duplicates
      imported.sessions.forEach((session: any) => {
        if (!currentData.sessions.find(s => s.id === session.id)) {
          currentData.sessions.push({
            ...session,
            createdAt: new Date(session.createdAt),
            updatedAt: new Date(session.updatedAt),
            messages: session.messages.map((msg: any) => ({
              ...msg,
              timestamp: new Date(msg.timestamp)
            }))
          });
        }
      });
      
      this.saveData(currentData);
      return true;
    } catch (error) {
      return false;
    }
  }
}

// Export singleton instance
export const chatStorage = ChatStorage.getInstance();

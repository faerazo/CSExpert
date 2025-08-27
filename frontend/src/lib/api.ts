// API configuration and utilities for CSExpert backend

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// Types for API responses
export interface ChatResponse {
  answer: string;
  content_type: string;
  sources: Source[];
  num_documents_retrieved: number;
  session_id?: string;
}

export interface Source {
  course_code: string;
  course_title: string;
  section: string;
  doc_type: string;
}

export interface SystemStatus {
  status: string;
  total_documents?: number;
  course_documents?: number;
  program_documents?: number;
  embedding_model?: string;
  llm_model?: string;
  collection_name?: string;
  error?: string;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
  chat_history?: Array<{
    role?: string;
    sender?: string;
    content: string;
    sources?: any[]; // Sources from AI responses for better context
  }>;
}

export interface ChatHistoryData {
  session_id: string;
  title: string;
  messages: any[];
  created_at: string;
  updated_at: string;
}

export interface ChatHistoryRequest {
  title?: string;
  messages: any[];
}

export interface ChatHistoryUpdate {
  title?: string;
  messages?: any[];
}

// API functions
export const api = {
  // Send a chat message
  async sendMessage(request: ChatRequest): Promise<ChatResponse> {
    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      throw error;
    }
  },

  // Get system status
  async getSystemStatus(): Promise<SystemStatus> {
    try {
      const response = await fetch(`${API_BASE_URL}/system/status`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      throw error;
    }
  },

  // Health check
  async healthCheck(): Promise<{ status: string; reason?: string }> {
    try {
      const response = await fetch(`${API_BASE_URL}/health`);
      return await response.json();
    } catch (error) {
      throw error;
    }
  },

  // Search documents
  async searchDocuments(query: string, docType?: string, limit: number = 10) {
    try {
      const params = new URLSearchParams({
        q: query,
        limit: limit.toString(),
      });
      
      if (docType) {
        params.append('doc_type', docType);
      }

      const response = await fetch(`${API_BASE_URL}/search?${params}`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      throw error;
    }
  },

  // Get courses
  async getCourses() {
    try {
      const response = await fetch(`${API_BASE_URL}/courses`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      throw error;
    }
  },

  // Get programs
  async getPrograms() {
    try {
      const response = await fetch(`${API_BASE_URL}/programs`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      throw error;
    }
  },

  // Chat History API (Optional backend persistence)
  async saveChatHistory(sessionId: string, data: ChatHistoryRequest): Promise<ChatHistoryData> {
    try {
      const response = await fetch(`${API_BASE_URL}/chat/history/${sessionId}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      throw error;
    }
  },

  async getChatHistory(sessionId: string): Promise<ChatHistoryData> {
    try {
      const response = await fetch(`${API_BASE_URL}/chat/history/${sessionId}`);
      
      if (!response.ok) {
        if (response.status === 404) {
          throw new Error('Chat history not found');
        }
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      throw error;
    }
  },

  async getAllChatHistories(limit: number = 50, offset: number = 0) {
    try {
      const params = new URLSearchParams({
        limit: limit.toString(),
        offset: offset.toString(),
      });

      const response = await fetch(`${API_BASE_URL}/chat/histories?${params}`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      throw error;
    }
  },

  async deleteChatHistory(sessionId: string): Promise<void> {
    try {
      const response = await fetch(`${API_BASE_URL}/chat/history/${sessionId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
    } catch (error) {
      throw error;
    }
  },

  async updateChatHistory(sessionId: string, update: ChatHistoryUpdate): Promise<ChatHistoryData> {
    try {
      const response = await fetch(`${API_BASE_URL}/chat/history/${sessionId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(update),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      throw error;
    }
  }
};

// Error handling utility
export const isApiError = (error: unknown): error is Error => {
  return error instanceof Error;
};

export const getErrorMessage = (error: unknown): string => {
  if (isApiError(error)) {
    return error.message;
  }
  return 'An unexpected error occurred';
}; 
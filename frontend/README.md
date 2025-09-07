# CSExpert Frontend

A modern React application providing an intuitive chat interface for the CSExpert backend API.

## Overview

The CSExpert frontend is a Single Page Application (SPA) built with React and TypeScript. It provides a conversational interface for users to interact with the University of Gothenburg's course and program information system.

### Key Features
- 💬 Real-time chat interface with message history
- 📱 Responsive design for desktop and mobile
- 🔄 Session management with localStorage persistence
- 📚 Source citation display with syllabus links
- ⚡ Optimized performance with Tanstack Query
- 🎨 Modern UI with Tailwind CSS and shadcn/ui

## Technology Stack

- **React 18** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **Tailwind CSS** - Utility-first styling
- **shadcn/ui** - UI component library
- **Tanstack Query** - Data fetching and caching
- **React Router** - Client-side routing

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── chat/              # Chat-specific components
│   │   │   ├── ChatInterface.tsx
│   │   │   ├── ChatMessage.tsx
│   │   │   ├── ChatInput.tsx
│   │   │   └── ChatHistory.tsx
│   │   ├── layout/            # Layout components
│   │   │   ├── MainLayout.tsx
│   │   │   └── Sidebar.tsx
│   │   └── ui/               # Reusable UI components
│   ├── hooks/                # Custom React hooks
│   │   ├── use-chat.tsx     # Main chat logic
│   │   ├── use-mobile.tsx   # Mobile detection
│   │   └── use-toast.ts     # Toast notifications
│   ├── lib/                  # Utilities
│   │   ├── api.ts           # API client
│   │   ├── chat-storage.ts  # LocalStorage management
│   │   └── utils.ts         # Helper functions
│   ├── pages/               # Page components
│   │   ├── Index.tsx        # Main chat page
│   │   └── NotFound.tsx     # 404 page
│   ├── App.tsx              # Root component
│   ├── main.tsx             # Entry point
│   └── index.css            # Global styles
├── public/                  # Static assets
├── dist/                    # Production build
├── package.json            # Dependencies
├── vite.config.ts          # Vite configuration
├── tailwind.config.ts      # Tailwind configuration
└── tsconfig.json           # TypeScript configuration
```

## Setup & Development

### Prerequisites

- Node.js 18.x or higher
- npm 9.x or higher

### Installation

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

### Environment Variables

Create a `.env` file for local development:

```env
# API endpoint (defaults to http://localhost:8000)
VITE_API_BASE_URL=http://localhost:8000
```

## Architecture

### Component Hierarchy

```
App
├── QueryClientProvider
├── TooltipProvider
└── BrowserRouter
    └── Routes
        └── Index
            └── MainLayout
                ├── Sidebar
                │   └── ChatHistory
                └── ChatInterface
                    ├── ChatMessage
                    └── ChatInput
```

### State Management

The application uses several state management approaches:

1. **Tanstack Query** - Server state (API responses, system status)
2. **React State** - Local UI state (loading, errors)
3. **LocalStorage** - Persistent state (chat sessions, preferences)
4. **URL State** - Navigation state (session IDs)

### Custom Hooks

#### `useChat`
Main hook managing chat functionality:
- Message sending and receiving
- Session management
- History persistence
- System status monitoring

```typescript
const {
  messages,
  isLoading,
  sendMessage,
  editMessage,
  clearConversation,
  sessionId,
  sessions,
  // ... more
} = useChat({ sessionId });
```

#### `useMobile`
Responsive design helper:
```typescript
const isMobile = useMobile(); // true if viewport < 768px
```

### API Integration

The `lib/api.ts` module provides typed API methods:

```typescript
// Send a chat message
const response = await api.sendMessage({
  message: "What is DIT199?",
  session_id: sessionId,
  chat_history: previousMessages
});

// Get system status
const status = await api.getSystemStatus();
```

## UI Components

### Chat Components

**ChatInterface** - Main chat container managing:
- Message display area
- Input handling
- System status display
- Loading states

**ChatMessage** - Individual message display with:
- User/AI message styling
- Markdown rendering
- Source citations
- Edit functionality

**ChatInput** - Message input with:
- Auto-resize textarea
- Send on Enter
- Disabled state handling

### Layout Components

**MainLayout** - Application shell providing:
- Responsive sidebar
- Mobile menu toggle
- Session management UI

**Sidebar** - Navigation and history:
- Chat session list
- New chat button
- Session actions (rename, delete)

## Styling

The application uses Tailwind CSS with custom configuration:

```css
/* Custom colors defined in tailwind.config.ts */
--brand-primary: #004B87    /* GU Blue */
--brand-secondary: #4A9FE6  /* Light Blue */
--brand-light: #E6F2FF      /* Very Light Blue */
```

### CSS Architecture

1. **Tailwind Utilities** - Primary styling method
2. **shadcn/ui Components** - Pre-styled components
3. **Custom CSS** - Minimal custom styles in `index.css`

## Performance Optimization

### Code Splitting
- Route-based splitting with React Router
- Lazy loading for heavy components

### Caching Strategy
- Tanstack Query caches API responses
- LocalStorage for session persistence
- Stale-while-revalidate for system status

### Bundle Optimization
- Vite tree-shaking
- CSS purging with Tailwind
- Minification in production

## Deployment

The frontend is deployed as part of the full application on Heroku:

1. Frontend is built during deployment
2. Static files served by FastAPI backend
3. Client-side routing handled by catch-all route


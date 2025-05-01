
import React from 'react';
import MainLayout from '@/components/layout/MainLayout';
import { ChatInterface } from '@/components/chat/ChatInterface';

const Index = () => {
  return (
    <MainLayout>
      <div className="flex flex-col h-full">
        <ChatInterface />
      </div>
    </MainLayout>
  );
};

export default Index;


import React from 'react';
import MainLayout from '@/components/layout/MainLayout';

const Admin = () => {
  return (
    <MainLayout>
      <div className="flex flex-col h-full">
        <div className="p-4">
          <h1 className="text-2xl font-bold text-brand-primary">Admin Dashboard</h1>
          <p className="text-gray-600 mt-2">
            Welcome to the RAG Admin Dashboard. Use this interface to manage documents and system settings.
          </p>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
            <div className="p-4 border rounded-lg bg-white shadow-sm">
              <h3 className="text-lg font-medium text-brand-primary">Documents</h3>
              <p className="text-2xl font-bold mt-2">0</p>
              <p className="text-sm text-gray-500 mt-2">Total documents uploaded</p>
            </div>
            
            <div className="p-4 border rounded-lg bg-white shadow-sm">
              <h3 className="text-lg font-medium text-brand-primary">Queries</h3>
              <p className="text-2xl font-bold mt-2">0</p>
              <p className="text-sm text-gray-500 mt-2">Chat queries today</p>
            </div>
            
            <div className="p-4 border rounded-lg bg-white shadow-sm">
              <h3 className="text-lg font-medium text-brand-primary">Processing</h3>
              <p className="text-2xl font-bold mt-2">0</p>
              <p className="text-sm text-gray-500 mt-2">Documents in processing</p>
            </div>
          </div>
        </div>
      </div>
    </MainLayout>
  );
};

export default Admin;

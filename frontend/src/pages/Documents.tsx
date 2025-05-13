
import React, { useState } from 'react';
import MainLayout from '@/components/layout/MainLayout';
import { DocumentUpload } from '@/components/admin/DocumentUpload';
import { DocumentList } from '@/components/admin/DocumentList';

const Documents = () => {
  // Mock documents data
  const [documents, setDocuments] = useState([
    {
      id: '1',
      name: 'Company_Policy.pdf',
      uploadDate: new Date(2023, 4, 15),
      size: 2.5 * 1024 * 1024,
      status: 'active' as const,
    },
    {
      id: '2',
      name: 'Product_Manual.pdf',
      uploadDate: new Date(2023, 4, 10),
      size: 4.2 * 1024 * 1024,
      status: 'active' as const,
    },
    {
      id: '3',
      name: 'Research_Paper.pdf',
      uploadDate: new Date(2023, 4, 5),
      size: 1.8 * 1024 * 1024,
      status: 'processing' as const,
    }
  ]);
  
  const handleDocumentUpload = (file: File) => {
    console.log('Uploading document:', file.name);
    // In a real implementation, this would upload the file to the server
    
    // Mock adding the document to the list
    const newDocument = {
      id: Date.now().toString(),
      name: file.name,
      uploadDate: new Date(),
      size: file.size,
      status: 'processing' as const,
    };
    
    setDocuments((prev) => [newDocument, ...prev]);
  };
  
  const handleDeleteDocument = (id: string) => {
    setDocuments((prev) => prev.filter((doc) => doc.id !== id));
  };
  
  const handleDownloadDocument = (id: string) => {
    console.log('Downloading document:', id);
    // In a real implementation, this would download the file from the server
  };
  
  return (
    <MainLayout>
      <div className="p-4">
        <h1 className="text-2xl font-bold text-brand-primary">Document Management</h1>
        
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
          <div className="lg:col-span-1">
            <DocumentUpload onDocumentUpload={handleDocumentUpload} />
          </div>
          
          <div className="lg:col-span-2">
            <div className="border rounded-lg">
              <div className="p-4 border-b">
                <h3 className="text-lg font-medium">Uploaded Documents</h3>
              </div>
              <DocumentList
                documents={documents}
                onDeleteDocument={handleDeleteDocument}
                onDownloadDocument={handleDownloadDocument}
              />
            </div>
          </div>
        </div>
      </div>
    </MainLayout>
  );
};

export default Documents;

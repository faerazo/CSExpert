
import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Upload, X, FileText } from 'lucide-react';

interface DocumentUploadProps {
  onDocumentUpload?: (file: File) => void;
}

export const DocumentUpload: React.FC<DocumentUploadProps> = ({
  onDocumentUpload
}) => {
  const [dragActive, setDragActive] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };
  
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      handleFile(file);
    }
  };
  
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      handleFile(file);
    }
  };
  
  const handleFile = (file: File) => {
    // Check if the file is a PDF
    if (file.type !== 'application/pdf') {
      alert('Please upload a PDF file');
      return;
    }
    
    setSelectedFile(file);
    onDocumentUpload?.(file);
  };
  
  const clearSelectedFile = () => {
    setSelectedFile(null);
  };
  
  return (
    <div className="p-4 border rounded-lg">
      <h3 className="text-lg font-medium mb-4">Upload Document</h3>
      
      {selectedFile ? (
        <div className="p-4 border rounded-lg bg-brand-light">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <FileText size={24} className="text-brand-primary" />
              <div className="ml-3">
                <div className="font-medium">{selectedFile.name}</div>
                <div className="text-sm text-gray-500">
                  {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                </div>
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={clearSelectedFile}
              className="text-gray-500 hover:text-brand-accent"
            >
              <X size={16} />
            </Button>
          </div>
          
          <div className="mt-4">
            <Button 
              className="bg-brand-accent hover:bg-brand-secondary text-white w-full"
              onClick={() => console.log('Processing file:', selectedFile.name)}
            >
              Process Document
            </Button>
          </div>
        </div>
      ) : (
        <div
          className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
            dragActive ? 'border-brand-primary bg-brand-light' : 'border-gray-300'
          }`}
          onDragEnter={handleDrag}
          onDragOver={handleDrag}
          onDragLeave={handleDrag}
          onDrop={handleDrop}
        >
          <input
            id="document-upload"
            type="file"
            accept=".pdf"
            onChange={handleChange}
            className="hidden"
          />
          
          <Upload size={48} className="mx-auto text-gray-400" />
          
          <p className="mt-2 text-sm text-gray-600">
            Drag and drop your PDF here, or
          </p>
          
          <label
            htmlFor="document-upload"
            className="mt-2 inline-block px-4 py-2 rounded-md bg-brand-primary text-white cursor-pointer hover:bg-brand-secondary transition-colors"
          >
            Browse Files
          </label>
          
          <p className="mt-2 text-xs text-gray-500">
            PDF files only, max 10MB
          </p>
        </div>
      )}
    </div>
  );
};

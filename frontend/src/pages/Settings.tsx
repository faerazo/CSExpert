
import React from 'react';
import MainLayout from '@/components/layout/MainLayout';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Slider } from '@/components/ui/slider';

const Settings = () => {
  return (
    <MainLayout>
      <div className="p-4">
        <h1 className="text-2xl font-bold text-brand-primary">Settings</h1>
        
        <div className="mt-6 p-4 border rounded-lg bg-white">
          <h2 className="text-xl font-semibold mb-4">RAG Configuration</h2>
          
          <div className="space-y-6">
            <div>
              <h3 className="text-md font-medium mb-2">Chat Settings</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Temperature
                  </label>
                  <div className="flex items-center gap-4">
                    <div className="flex-1">
                      <Slider
                        defaultValue={[0.7]}
                        max={1}
                        step={0.1}
                        className="w-full"
                      />
                    </div>
                    <span className="text-sm font-medium">0.7</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Controls randomness: Lower values are more focused, higher values more creative.
                  </p>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Response Length (max tokens)
                  </label>
                  <Input type="number" defaultValue={1024} />
                </div>
              </div>
            </div>
            
            <div>
              <h3 className="text-md font-medium mb-2">Retrieval Settings</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Number of chunks to retrieve
                  </label>
                  <Input type="number" defaultValue={5} />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Relevance Threshold
                  </label>
                  <div className="flex items-center gap-4">
                    <div className="flex-1">
                      <Slider
                        defaultValue={[0.8]}
                        max={1}
                        step={0.01}
                        className="w-full"
                      />
                    </div>
                    <span className="text-sm font-medium">0.80</span>
                  </div>
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Chunk Size (tokens)
                  </label>
                  <Input type="number" defaultValue={512} />
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Chunk Overlap (tokens)
                  </label>
                  <Input type="number" defaultValue={50} />
                </div>
              </div>
            </div>
          </div>
          
          <div className="mt-6 flex justify-end">
            <Button 
              className="bg-brand-accent hover:bg-brand-secondary text-white"
              onClick={() => console.log('Save settings')}
            >
              Save Settings
            </Button>
          </div>
        </div>
      </div>
    </MainLayout>
  );
};

export default Settings;

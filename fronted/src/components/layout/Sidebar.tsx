import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';

export const Sidebar: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  
  // Check if the current path is an admin path
  const isAdmin = location.pathname.includes('/admin');
  
  // Define navigation links, filtering admin links based on path
  const navigation = [
    { name: 'Chat', path: '/' },
    ...(isAdmin ? [
      { name: 'Admin', path: '/admin' },
      { name: 'Documents', path: '/admin/documents' },
      { name: 'Settings', path: '/admin/settings' },
    ] : [])
  ];

  const isActive = (path: string) => {
    if (path === '/') {
      return location.pathname === '/';
    }
    return location.pathname.startsWith(path);
  };
  
  return (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="p-4 border-b border-brand-medium">
        <div className="flex flex-col items-center">
          <img
            src="https://media.licdn.com/dms/image/v2/D4E0BAQEGltszpDpx3w/company-logo_200_200/company-logo_200_200/0/1665142883299/university_of_gothenburg_logo?e=2147483647&v=beta&t=NNyVbo6ITZdNXlFypJA6AVp3wtgY5dtO4hjNx3JM6oU"
            alt="CSExpert Logo"
            className="h-24 w-24 object-contain"
          />
          <span className="mt-3 text-xl font-bold text-brand-primary">CSExpert</span>
          <div className="text-xs text-brand-secondary mt-1 text-center">
            Course questions? I have answers
          </div>
        </div>
      </div>
      
      {/* Navigation links */}
      <nav className="flex-1 px-2 py-4 space-y-1 overflow-y-auto">
        {navigation.map((item) => (
          <a
            key={item.name}
            onClick={() => navigate(item.path)}
            className={cn(
              isActive(item.path)
                ? 'bg-brand-light text-brand-primary font-medium'
                : 'text-gray-600 hover:bg-brand-light hover:text-brand-primary',
              'group flex items-center px-3 py-2 text-base rounded-md cursor-pointer transition-colors'
            )}
          >
            {item.name}
          </a>
        ))}
      </nav>
      
      {/* User section - removed since no user accounts are needed */}
      {isAdmin && (
        <div className="p-4 border-t border-brand-medium">
          <div className="text-sm font-medium text-gray-900">Admin Panel</div>
          <div className="text-xs text-gray-500">Restricted Access</div>
        </div>
      )}
    </div>
  );
};

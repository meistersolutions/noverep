import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import App from './App';
import { initCapacitorShell } from '@/lib/capacitorInit';
import { AuthBootstrap } from '@/components/AuthBootstrap';
import './index.css';

void initCapacitorShell();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthBootstrap>
        <App />
        <Toaster
          position="bottom-right"
          toastOptions={{
            className: 'glass !bg-surface-raised !text-white',
          }}
        />
      </AuthBootstrap>
    </BrowserRouter>
  </React.StrictMode>,
);

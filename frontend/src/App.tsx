import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import { AuthProvider } from './hooks/useAuth';
import { queryClient } from './lib/query-client';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';

// Lazy-loaded pages (code splitting)
const LoginPage = lazy(() => import('./pages/LoginPage'));
const ProvidersPage = lazy(() => import('./pages/ProvidersPage'));
const ModelsPage = lazy(() => import('./pages/ModelsPage'));
const ApiKeysPage = lazy(() => import('./pages/ApiKeysPage'));
const UsagePage = lazy(() => import('./pages/UsagePage'));
const StatusPage = lazy(() => import('./pages/StatusPage'));

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Suspense fallback={<div className="min-h-screen bg-background flex items-center justify-center text-muted-foreground">Loading...</div>}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/status" element={<StatusPage />} />
              <Route
                element={
                  <ProtectedRoute>
                    <Layout />
                  </ProtectedRoute>
                }
              >
                <Route index element={<ProvidersPage />} />
                <Route path="models" element={<ModelsPage />} />
                <Route path="keys" element={<ApiKeysPage />} />
                <Route path="usage" element={<UsagePage />} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
          <Toaster theme="dark" position="bottom-right" />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;

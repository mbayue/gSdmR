import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import apiClient from '../api/client';
import type { LoginRequest } from '../types';

interface AuthContextType {
  token: string | null;
  username: string | null;
  login: (credentials: LoginRequest) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [username, setUsername] = useState<string | null>(null);

  useEffect(() => {
    if (token) {
      apiClient.get('/api/auth/me')
        .then((res) => setUsername(res.data.username))
        .catch(() => {
          setToken(null);
          setUsername(null);
          localStorage.removeItem('token');
        });
    }
  }, [token]);

  const login = async (credentials: LoginRequest) => {
    const res = await apiClient.post('/api/auth/login', credentials);
    const accessToken = res.data.access_token;
    localStorage.setItem('token', accessToken);
    setToken(accessToken);
    setUsername(credentials.username);
  };

  const logout = () => {
    localStorage.removeItem('token');
    setToken(null);
    setUsername(null);
  };

  return (
    <AuthContext.Provider value={{ token, username, login, logout, isAuthenticated: !!token }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

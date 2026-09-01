import { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';
import type { User, AuthTokens, LoginRequest, RegisterRequest, AuthResponse } from '../types/auth';
import { apiClient } from '../api/client';
import type { SuccessResponse } from '../types/api';

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (data: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function toUser(raw: User): User {
  return {
    id: raw.id,
    email: raw.email,
    name: raw.name,
    role: raw.role,
  };
}

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const checkAuth = async () => {
    const tokens = localStorage.getItem('auth_tokens');
    if (tokens) {
      try {
        const response = await apiClient.get<SuccessResponse<User>>('/auth/me');
        setUser(toUser(response.data.data));
      } catch (error) {
        localStorage.removeItem('auth_tokens');
        setUser(null);
      }
    }
    setIsLoading(false);
  };

  useEffect(() => {
    checkAuth();

    const handleUnauthorized = () => {
      setUser(null);
      localStorage.removeItem('auth_tokens');
    };

    window.addEventListener('auth_unauthorized', handleUnauthorized);
    return () => {
      window.removeEventListener('auth_unauthorized', handleUnauthorized);
    };
  }, []);

  const login = async (data: LoginRequest) => {
    const response = await apiClient.post<SuccessResponse<AuthResponse>>('/auth/login', data);
    const { user: userData, access_token, refresh_token } = response.data.data;

    const tokens: AuthTokens = { access_token, refresh_token };
    localStorage.setItem('auth_tokens', JSON.stringify(tokens));
    setUser(toUser(userData));
  };

  const register = async (data: RegisterRequest) => {
    const response = await apiClient.post<SuccessResponse<AuthResponse>>('/auth/register', data);
    const { user: userData, access_token, refresh_token } = response.data.data;

    const tokens: AuthTokens = { access_token, refresh_token };
    localStorage.setItem('auth_tokens', JSON.stringify(tokens));
    setUser(toUser(userData));
  };

  const logout = () => {
    localStorage.removeItem('auth_tokens');
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

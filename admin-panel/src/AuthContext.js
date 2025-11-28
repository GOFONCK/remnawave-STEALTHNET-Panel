import React, { createContext, useState, useContext, useEffect } from 'react';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [token, setToken] = useState(null);
  const [role, setRole] = useState(null); 
  const [currency, setCurrency] = useState('uah'); 
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // ❗️❗️❗️ ИЗМЕНЕНА: Регистрация (больше не логинит) ❗️❗️❗️
  const register = async (email, password, refCode) => { 
    const response = await fetch('/api/public/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, ref_code: refCode }), 
    });
    
    const data = await response.json();
    if (!response.ok) {
      const errorMsg = data.errors ? data.errors[0].message : data.message;
      throw new Error(errorMsg || 'Ошибка регистрации');
    }
    
    // ❗️ УСПЕХ: Просто возвращаем сообщение
    return data; // (Вернет { message: "Регистрация успешна. Пожалуйста..." })
  };

  // ❗️ ИЗМЕНЕНА: Вход (ловит 'NOT_VERIFIED')
  const login = async (email, password) => {
    const response = await fetch('/api/public/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });

    const data = await response.json();
    
    // ❗️ Новая обработка ошибок
    if (!response.ok) {
        // Если код 403 и "NOT_VERIFIED", кидаем особую ошибку
        if (response.status === 403 && data.code === "NOT_VERIFIED") {
            throw new Error("NOT_VERIFIED");
        }
        throw new Error(data.message || 'Ошибка входа');
    }

    const newToken = data.token;
    const newRole = data.role;
    
    if (newToken && newRole) {
      setToken(newToken);
      setRole(newRole); 
      localStorage.setItem('userToken', newToken);
      localStorage.setItem('userRole', newRole); 
      return { token: newToken, role: newRole };
    } else {
      throw new Error('Токен или роль не были получены');
    }
  };

  // --- (logout, useEffect - БЕЗ ИЗМЕНЕНИЙ) ---
  const logout = () => {
    setToken(null);
    setRole(null); 
    setUser(null);
    setCurrency('uah'); 
    localStorage.removeItem('userToken');
    localStorage.removeItem('userRole'); 
    localStorage.removeItem('userCurrency'); 
  };

  useEffect(() => {
    const storedToken = localStorage.getItem('userToken');
    const storedRole = localStorage.getItem('userRole'); 
    const storedCurrency = localStorage.getItem('userCurrency'); 
    if (storedToken && storedRole) {
      setToken(storedToken);
      setRole(storedRole); 
    }
    if (storedCurrency) {
        setCurrency(storedCurrency); 
    }
    setLoading(false); 
  }, []);

  const value = {
    token, role, user, setUser,
    setToken, setRole, // Добавляем для автоматической авторизации
    login, logout, register,
    loading, currency, setCurrency,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export const useAuth = () => {
  return useContext(AuthContext);
};
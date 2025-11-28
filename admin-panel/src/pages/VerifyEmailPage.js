import React, { useState, useEffect } from 'react';
import { useSearchParams, Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../AuthContext';

function VerifyEmailPage() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { setToken, setRole, setUser } = useAuth();
  const [status, setStatus] = useState('verifying'); // verifying | success | error
  const [error, setError] = useState('');

  useEffect(() => {
    const token = searchParams.get('token');
    
    if (!token) {
      setStatus('error');
      setError(t('verify.error_no_token')); // 'Токен не найден.'
      return;
    }

    const verifyToken = async () => {
      try {
        const response = await fetch('/api/public/verify-email', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: token })
        });
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.message || 'Ошибка верификации');
        }
        
        // Автоматическая авторизация после верификации
        if (data.token && data.role) {
          setToken(data.token);
          setRole(data.role);
          // Сохраняем в localStorage
          localStorage.setItem('userToken', data.token);
          localStorage.setItem('userRole', data.role);
          
          // Загружаем данные пользователя
          try {
            const userResponse = await fetch('/api/client/me', {
              headers: { 'Authorization': `Bearer ${data.token}` }
            });
            if (userResponse.ok) {
              const userData = await userResponse.json();
              setUser(userData);
            }
          } catch (e) {
            console.error('Ошибка загрузки данных пользователя:', e);
          }
          
          // Перенаправляем в панель в зависимости от роли
          setTimeout(() => {
            if (data.role === 'admin') {
              navigate('/admin/dashboard');
            } else {
              navigate('/dashboard/subscription');
            }
          }, 1000);
        }
        
        setStatus('success');
        
      } catch (e) {
        setStatus('error');
        setError(e.message);
      }
    };
    
    verifyToken();
  }, [searchParams, t, navigate, setToken, setRole, setUser]);

  return (
    <div className="container">
      {status === 'verifying' && (
        <>
          <h2>{t('verify.verifying_title', 'Верификация...')}</h2>
          <div className="loading-mini" style={{textAlign: 'center'}}>{t('verify.verifying_text', 'Пожалуйста, подождите...')}</div>
        </>
      )}
      
      {status === 'success' && (
        <>
          <h2 style={{color: 'var(--accent-green)'}}>✅ {t('verify.success_title', 'Успешно!')}</h2>
          <p style={{textAlign: 'center'}}>{t('verify.success_text', 'Ваш email подтвержден. Перенаправление в панель...')}</p>
        </>
      )}
      
      {status === 'error' && (
        <>
          <h2 style={{color: 'var(--accent-red)'}}>❌ {t('verify.error_title', 'Ошибка')}</h2>
          <div className="message-error" style={{textAlign: 'center'}}>
            {error || t('verify.error_generic', 'Произошла неизвестная ошибка.')}
          </div>
          {/* ❗️ ИСПРАВЛЕНИЕ: Убран style={{textAlign: 'center'}} */}
          <Link to="/login" className="btn btn-outline" style={{marginTop: '15px'}}>
            {t('verify.go_to_login', 'Перейти ко входу')}
          </Link>
        </>
      )}
    </div>
  );
}

export default VerifyEmailPage;
import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';
import { useNavigate, useLocation, Link, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { LuShieldCheck } from 'react-icons/lu'; // Иконка логотипа

// --- Компонент Входа ---
const LoginForm = ({ onLogin }) => {
  const { t } = useTranslation(); 
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const [notVerifiedError, setNotVerifiedError] = useState(false);
  const [resendStatus, setResendStatus] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null); setNotVerifiedError(false); setResendStatus(null); setLoading(true);
    try {
      const { role } = await login(email, password);
      onLogin(role); 
    } catch (err) {
      if (err.message === "NOT_VERIFIED") {
        setNotVerifiedError(true); setError(t('auth.error_not_verified'));
      } else { setError(err.message || t('auth.error_login')); }
      setLoading(false);
    }
  };
  
  const handleResendVerification = async () => {
    setResendStatus('sending'); setError(null);
    try {
      const response = await fetch('/api/public/resend-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message);
      setResendStatus('success');
    } catch (e) { setError(e.message); setResendStatus(null); }
  };

  return (
    <form onSubmit={handleSubmit} className="auth-form">
      <div className="form-group">
        <label htmlFor="email">{t('auth.email')}</label>
        <input type="email" id="email" value={email} onChange={(e) => setEmail(e.target.value)} required disabled={loading} placeholder="name@example.com" />
      </div>
      <div className="form-group">
        <label htmlFor="password">{t('auth.password')}</label>
        <input type="password" id="password" value={password} onChange={(e) => setPassword(e.target.value)} required disabled={loading} placeholder="••••••••" />
      </div>
      
      {error && <div className="message-error">{error}</div>}
      
      {notVerifiedError && (
        <div className="resend-container">
          <button type="button" className="btn-resend" disabled={resendStatus === 'sending'} onClick={handleResendVerification}>
            {resendStatus === 'sending' ? t('auth.resending') : t('auth.resend_button')}
          </button>
          {resendStatus === 'success' && <span className="resend-success">✅ {t('auth.resend_success')}</span>}
        </div>
      )}
      
      <button type="submit" className="btn btn-primary-glow" disabled={loading || resendStatus === 'sending'}>
        {loading ? '...' : t('auth.login_button')}
      </button>
    </form>
  );
};

// --- Компонент Регистрации ---
const RegisterForm = ({ onRegister }) => {
  const { t } = useTranslation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const [searchParams] = useSearchParams();
  const refCode = searchParams.get('ref'); 

  const handleSubmit = async (e) => {
    e.preventDefault(); setError(null); setSuccess(null); setLoading(true);
    try {
      const data = await register(email, password, refCode);
      setSuccess(data.message); setEmail(''); setPassword('');
    } catch (err) { setError(err.message || t('auth.error_register')); } 
    finally { setLoading(false); }
  };

  return (
    <form onSubmit={handleSubmit} className="auth-form">
      {error && <div className="message-error">{error}</div>}
      {success && <div className="message-success">{success}</div>}
      
      {refCode && !success && (
        <div className="referral-badge">
          {t('auth.invited_by')} <strong>{refCode}</strong>
        </div>
      )}
      
      <div className="form-group">
        <label htmlFor="email">{t('auth.email')}</label>
        <input type="email" id="email" value={email} onChange={(e) => setEmail(e.target.value)} required disabled={loading} placeholder="name@example.com" />
      </div>
      <div className="form-group">
        <label htmlFor="password">{t('auth.password')}</label>
        <input type="password" id="password" value={password} onChange={(e) => setPassword(e.target.value)} required disabled={loading} placeholder="••••••••" />
      </div>
      
      <button type="submit" className="btn btn-primary-glow" disabled={loading}>
        {loading ? '...' : t('auth.register_button')}
      </button>
    </form>
  );
};


// --- Главная страница AuthPage (С НОВЫМ ДИЗАЙНОМ) ---
function AuthPage() {
  const { t } = useTranslation(); 
  const location = useLocation();
  const navigate = useNavigate(); 
  const [isLoginView, setIsLoginView] = useState(location.pathname === '/login');

  useEffect(() => {
    setIsLoginView(location.pathname === '/login');
  }, [location.pathname]);

  const handleAuthSuccess = (role) => {
    if (role === 'ADMIN') navigate('/admin');
    else navigate('/dashboard');
  };

  return (
    <div className="auth-page-wrapper">
      <div className="auth-card">
        
        {/* ❗️ ЛОГОТИП И ЗАГОЛОВОК */}
        <div className="auth-header">
          <div className="auth-logo">
            <LuShieldCheck />
          </div>
          <h1>STEALTH<span className="text-accent">NET</span></h1>
          <p className="auth-subtitle">
            {isLoginView ? "Добро пожаловать в будущее безопасности." : "Присоединяйтесь к невидимой сети."}
          </p>
        </div>

        {/* ПЕРЕКЛЮЧАТЕЛЬ */}
        <div className="auth-tabs">
          <Link to="/login" className={`auth-tab ${isLoginView ? 'active' : ''}`}>
            {t('auth.login')}
          </Link>
          <Link to="/register" state={location.state} search={location.search} className={`auth-tab ${!isLoginView ? 'active' : ''}`}>
            {t('auth.register')}
          </Link>
        </div>

        {isLoginView ? 
          <LoginForm onLogin={handleAuthSuccess} /> : 
          <RegisterForm onRegister={handleAuthSuccess} />
        }
        
        <div className="auth-footer">
          &copy; 2025 StealthNET. Privacy First.
        </div>
      </div>
    </div>
  );
}

export default AuthPage;
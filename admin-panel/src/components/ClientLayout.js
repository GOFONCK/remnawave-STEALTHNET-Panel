import React, { useEffect, useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { useTranslation } from 'react-i18next';
import { 
  LuLayoutDashboard, LuServer, LuShieldCheck, 
  LuUsers, LuLifeBuoy, LuLogOut,
  LuLanguages, LuBanknote, LuSun, LuMoon,
  LuMenu, LuX 
} from 'react-icons/lu';
import { useTheme } from '../ThemeContext'; 

// --- Компонент: Переключатель темы ---
const ThemeSwitcherImpl = () => {
  const { theme, toggleTheme } = useTheme();
  return (
    <button className="btn-icon" onClick={toggleTheme} title={theme === 'light' ? 'Включить темную' : 'Включить светлую'}>
      {theme === 'light' ? <LuMoon /> : <LuSun />}
    </button>
  );
};

// --- Компонент Переключателей ---
const LanguageCurrencySwitcherImpl = () => {
  const { t, i18n } = useTranslation();
  const { token, user, setUser, currency, setCurrency } = useAuth(); 
  const currentLang = i18n.resolvedLanguage;
  const currentCurrency = currency;

  const saveSettings = async (settingsToSave) => {
    if (!token) return; 
    try {
      await fetch('http://127.0.0.1:5000/api/client/settings', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(settingsToSave)
      });
    } catch (e) { console.error("Не удалось сохранить настройки", e); }
  };

  const changeLanguage = (lng) => {
    i18n.changeLanguage(lng); 
    if (user) setUser(prevUser => ({ ...prevUser, preferred_lang: lng }));
    saveSettings({ lang: lng });
  };
  
  const changeCurrency = (curr) => {
    setCurrency(curr);
    localStorage.setItem('userCurrency', curr);
    if (user) setUser(prevUser => ({ ...prevUser, preferred_currency: curr }));
    saveSettings({ currency: curr });
  };

  return (
    <div className="settings-switcher">
      <div className="setting-control">
        <label htmlFor="currency-select"><LuBanknote /></label>
        <select id="currency-select" value={currentCurrency} onChange={(e) => changeCurrency(e.target.value)} className="lang-select">
          <option value="uah">₴ UAH</option>
          <option value="rub">₽ RUB</option>
          <option value="usd">$ USD</option>
        </select>
      </div>
      <div className="setting-control">
        <label htmlFor="lang-select"><LuLanguages /></label>
        <select id="lang-select" value={currentLang} onChange={(e) => changeLanguage(e.target.value)} className="lang-select">
          <option value="ru">{t('languages.ru')}</option>
          <option value="ua">{t('languages.ua')}</option>
          <option value="cn">{t('languages.cn')}</option>
          <option value="en">{t('languages.en')}</option>
        </select>
      </div>
    </div>
  );
};


// --- Основной компонент ClientLayout ---
export default function ClientLayout() {
  const { t, i18n } = useTranslation();
  const { user, setUser, logout, token, currency, setCurrency } = useAuth();
  const navigate = useNavigate();
  
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  useEffect(() => {
    if (user || !token) return; 
    const fetchMeData = async () => {
      try {
        const response = await fetch('/api/client/me', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) {
          if (response.status === 401) logout(); 
          throw new Error('Ошибка загрузки');
        }
        const data = await response.json();
        const userData = data.response || data;
        setUser(userData); 
        
        if(userData.preferred_lang && i18n.resolvedLanguage !== userData.preferred_lang) {
            i18n.changeLanguage(userData.preferred_lang);
        }
        if(userData.preferred_currency && currency !== userData.preferred_currency) {
            setCurrency(userData.preferred_currency);
            localStorage.setItem('userCurrency', userData.preferred_currency);
        }
      } catch (err) { console.error(err); } 
    };
    fetchMeData();
  }, [token, user, setUser, logout, i18n, currency, setCurrency]);

  const handleLogout = () => {
    logout();
    navigate('/login'); 
  };
  
  const closeSidebar = () => setIsSidebarOpen(false);

  if (!user) {
    return <div className="loading-full">Загрузка кабинета...</div>
  }

  return (
    <div className="client-shell">
      {isSidebarOpen && (
        <div className="sidebar-overlay" onClick={closeSidebar}></div>
      )}
      
      <nav className={`client-sidebar ${isSidebarOpen ? 'is-open' : ''}`}>
        <div className="sidebar-header">
          <div className="logo-mark">SN</div>
          <div className="sidebar-brand">
            <div className="logo">StealthNET</div>
            <span>Secure VPN</span>
          </div>
          <button className="btn-icon mobile-close-btn" onClick={closeSidebar} aria-label="Закрыть меню">
            <LuX />
          </button>
        </div>

        <div className="sidebar-body">
          <p className="sidebar-section-label">{t('sidebar.client_area', 'Личный кабинет')}</p>
          <ul className="sidebar-nav">
            <li><NavLink to="/dashboard/subscription" onClick={closeSidebar}><LuLayoutDashboard /> {t('sidebar.status')}</NavLink></li>
            <li><NavLink to="/dashboard/servers" onClick={closeSidebar}><LuServer /> {t('sidebar.servers')}</NavLink></li>
            <li><NavLink to="/dashboard/tariffs" onClick={closeSidebar}><LuShieldCheck /> {t('sidebar.tariffs')}</NavLink></li>
            <li><NavLink to="/dashboard/referrals" onClick={closeSidebar}><LuUsers /> {t('sidebar.referrals')}</NavLink></li>
            <li><NavLink to="/dashboard/support" onClick={closeSidebar}><LuLifeBuoy /> {t('sidebar.support')}</NavLink></li>
          </ul>
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-cta">
            <p>{t('sidebar.ready_to_upgrade', 'Готовы улучшить скорость?')}</p>
            <button className="btn btn-primary" onClick={() => { navigate('/dashboard/tariffs'); closeSidebar(); }}>
              {t('sidebar.choose_plan', 'Выбрать тариф')}
            </button>
          </div>
          <button onClick={handleLogout} className="btn-logout">
            <LuLogOut /> {t('header.logout')}
          </button>
        </div>
      </nav>

      <div className="client-main">
        <header className="client-toolbar">
          <div className="toolbar-left">
            <button 
              className="btn-icon mobile-menu-toggle" 
              onClick={() => setIsSidebarOpen(true)}
              aria-label="Открыть меню"
            >
              <LuMenu />
            </button>
            <div className="toolbar-title">
              <p>StealthNET VPN</p>
              <h1>{t('sidebar.dashboard_title', 'Панель клиента')}</h1>
            </div>
          </div>

          <div className="toolbar-actions">
            <LanguageCurrencySwitcherImpl />
            <ThemeSwitcherImpl /> 
            <button className="btn-ghost" onClick={() => navigate('/dashboard/tariffs')}>
              {t('sidebar.upgrade', 'Тарифы')}
            </button>
            <span className="user-chip">{user.email}</span>
          </div>
        </header>
        
        <main className="client-main-scroll">
          <Outlet /> 
        </main>
      </div>
    </div>
  );
}
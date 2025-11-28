import React, { useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { useTheme } from '../ThemeContext';
import { useTranslation } from 'react-i18next';
import { 
  LuLayoutDashboard,
  LuUsers, LuShieldCheck, LuTicket, 
  LuGift, LuLogOut, LuLifeBuoy,
  LuCreditCard, LuSun, LuMoon, LuMenu, LuX, LuServer, LuSettings, LuMail
} from 'react-icons/lu';

// --- Компонент: Переключатель темы ---
const ThemeSwitcherImpl = () => {
  const { theme, toggleTheme } = useTheme();
  return (
    <button className="btn-icon" onClick={toggleTheme} title={theme === 'light' ? 'Включить темную' : 'Включить светлую'}>
      {theme === 'light' ? <LuMoon /> : <LuSun />}
    </button>
  );
};

export default function AdminLayout() {
  const { t } = useTranslation();
  const { logout, user } = useAuth();
  const navigate = useNavigate();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login'); 
  };

  const closeSidebar = () => setIsSidebarOpen(false);

  return (
    <div className="admin-layout">
      {/* 1. Боковое меню */}
      <nav className={`admin-sidebar ${isSidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <div className="logo">STEALTHNET</div>
          <span>Admin Panel</span>
          <button className="btn-icon sidebar-close" onClick={closeSidebar}>
            <LuX />
          </button>
        </div>
        
        <ul className="sidebar-nav">
          <li>
            <NavLink to="/admin/dashboard" onClick={closeSidebar}>
              <LuLayoutDashboard /> Дашборд
            </NavLink>
          </li>
          <li>
            <NavLink to="/admin/users" onClick={closeSidebar}>
              <LuUsers /> Пользователи
            </NavLink>
          </li>
          <li>
            <NavLink to="/admin/tariffs" onClick={closeSidebar}>
              <LuShieldCheck /> Тарифы
            </NavLink>
          </li>
          <li>
            <NavLink to="/admin/promocodes" onClick={closeSidebar}>
              <LuTicket /> Промокоды
            </NavLink>
          </li>
          <li>
            <NavLink to="/admin/referrals" onClick={closeSidebar}>
              <LuGift /> Рефералы
            </NavLink>
          </li>
          <li>
            <NavLink to="/admin/support" onClick={closeSidebar}>
              <LuLifeBuoy /> Поддержка
            </NavLink>
          </li>
          <li>
            <NavLink to="/admin/payments" onClick={closeSidebar}>
              <LuCreditCard /> Платежи
            </NavLink>
          </li>
          <li>
            <NavLink to="/admin/squads" onClick={closeSidebar}>
              <LuServer /> Сквады
            </NavLink>
          </li>
          <li>
            <NavLink to="/admin/tariff-features" onClick={closeSidebar}>
              <LuShieldCheck /> Функции тарифов
            </NavLink>
          </li>
          <li>
            <NavLink to="/admin/system-settings" onClick={closeSidebar}>
              <LuSettings /> Системные настройки
            </NavLink>
          </li>
          <li>
            <NavLink to="/admin/broadcast" onClick={closeSidebar}>
              <LuMail /> {t('broadcast.title')}
            </NavLink>
          </li>
        </ul>
        
        <div className="sidebar-footer">
          {user && <div className="admin-user-info">{user.email}</div>}
          <button onClick={handleLogout} className="btn-logout">
            <LuLogOut /> Выйти
          </button>
        </div>
      </nav>

      {/* 2. Контент страницы */}
      <main className="admin-main-content">
        <header className="admin-toolbar">
          <button 
            className="btn-icon mobile-menu-toggle" 
            onClick={() => setIsSidebarOpen(true)}
            aria-label="Открыть меню"
          >
            <LuMenu />
          </button>
          <div className="toolbar-title">
            <h1>Панель администратора</h1>
          </div>
          <div className="toolbar-actions">
            <ThemeSwitcherImpl />
          </div>
        </header>
        <div className="admin-page-wrapper">
          <Outlet /> 
        </div>
      </main>
    </div>
  );
}
import React, { Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './AuthContext';
import './App.css'; 

// --- Page Imports ---
import AuthPage from './pages/AuthPage';
import VerifyEmailPage from './pages/VerifyEmailPage'; // ❗️ Страница верификации

// --- Client Page Imports ---
import ClientStatusPage from './pages/client/ClientStatusPage';
import ClientServersPage from './pages/client/ClientServersPage';
import ClientTariffsPage from './pages/client/ClientTariffsPage';
import ClientReferralsPage from './pages/client/ClientReferralsPage';
import ClientSupportPage from './pages/client/ClientSupportPage';

// --- Admin Page Imports ---
import AdminDashboardPage from './pages/AdminDashboardPage'; 
import AdminUsersPage from './pages/AdminUsersPage';
import AdminTariffsPage from './pages/AdminTariffsPage';
import AdminPromoCodesPage from './pages/AdminPromoCodesPage';
import AdminReferralsPage from './pages/AdminReferralsPage'; 
import AdminSupportPage from './pages/AdminSupportPage';
import AdminPaymentsPage from './pages/AdminPaymentsPage'; 
import AdminSquadsPage from './pages/AdminSquadsPage';
import AdminTariffFeaturesPage from './pages/AdminTariffFeaturesPage';
import AdminSystemSettingsPage from './pages/AdminSystemSettingsPage';
import AdminBroadcastPage from './pages/AdminBroadcastPage'; 

// --- Layout Imports ---
import AdminLayout from './components/AdminLayout'; 
import ClientLayout from './components/ClientLayout'; 

// --- Route Guards (Security) ---

// Guard for CLIENTS (must be logged in, must be CLIENT)
const PrivateRoute = ({ children }) => {
  const { token, role, loading } = useAuth(); 
  if (loading) return <div className="loading-full">Загрузка...</div>;
  if (!token) return <Navigate to="/login" replace />; 
  return role === 'CLIENT' ? children : <Navigate to="/admin" replace />; 
};

// Guard for ADMINS (must be logged in, must be ADMIN)
const AdminRoute = ({ children }) => {
  const { token, role, loading } = useAuth();
  if (loading) return <div className="loading-full">Загрузка...</div>;
  if (!token) return <Navigate to="/login" replace />;
  return role === 'ADMIN' ? children : <Navigate to="/dashboard" replace />;
};

// Guard for GUESTS (must NOT be logged in)
const PublicOnlyRoute = ({ children }) => {
  const { token, loading } = useAuth();
  if (loading) return <div className="loading-full">Загрузка...</div>;
  return token ? <Navigate to="/" replace /> : children;
};

// Smart redirect for the root URL ("/")
const RootRedirect = () => {
  const { token, role, loading } = useAuth();
  if (loading) return <div className="loading-full">Загрузка...</div>;
  if (!token) return <Navigate to="/login" replace />;
  return <Navigate to={role === 'ADMIN' ? '/admin' : '/dashboard'} replace />;
};
// --- End of Route Guards ---


function App() {
  return (
    <div className="App">
      <Suspense fallback={<div className="loading-full">Загрузка...</div>}>
        <Routes>
          {/* 1. Root Redirect */}
          <Route path="/" element={<RootRedirect />} />
          
          {/* 2. Public Pages (Login/Register) */}
          <Route path="/login" element={<PublicOnlyRoute><AuthPage /></PublicOnlyRoute>} />
          <Route path="/register" element={<PublicOnlyRoute><AuthPage /></PublicOnlyRoute>} />
          
          {/* ❗️ НОВЫЙ МАРШРУТ ВЕРИФИКАЦИИ ❗️ */}
          <Route path="/verify" element={<VerifyEmailPage />} />
          
          {/* 3. Client Dashboard */}
          <Route 
            path="/dashboard" 
            element={<PrivateRoute><ClientLayout /></PrivateRoute>} 
          >
            <Route path="subscription" element={<ClientStatusPage />} />
            <Route path="servers" element={<ClientServersPage />} />
            <Route path="tariffs" element={<ClientTariffsPage />} />
            <Route path="referrals" element={<ClientReferralsPage />} />
            <Route path="support" element={<ClientSupportPage />} />
            <Route path="support/:ticketId" element={<ClientSupportPage />} />
            <Route index element={<Navigate to="/dashboard/subscription" replace />} />
          </Route>
          
          {/* 4. Admin Panel */}
          <Route 
            path="/admin" 
            element={<AdminRoute><AdminLayout /></AdminRoute>}
          >
            <Route path="dashboard" element={<AdminDashboardPage />} /> 
            <Route path="users" element={<AdminUsersPage />} />
            <Route path="tariffs" element={<AdminTariffsPage />} />
            <Route path="promocodes" element={<AdminPromoCodesPage />} />
            <Route path="referrals" element={<AdminReferralsPage />} />
            <Route path="support" element={<AdminSupportPage />} />
            <Route path="support/:ticketId" element={<AdminSupportPage />} />
            <Route path="payments" element={<AdminPaymentsPage />} />
            <Route path="squads" element={<AdminSquadsPage />} />
            <Route path="tariff-features" element={<AdminTariffFeaturesPage />} />
            <Route path="system-settings" element={<AdminSystemSettingsPage />} />
            <Route path="broadcast" element={<AdminBroadcastPage />} />
            
            <Route index element={<Navigate to="/admin/dashboard" replace />} />
          </Route>
          
        </Routes>
      </Suspense>
    </div>
  );
}

export default App;
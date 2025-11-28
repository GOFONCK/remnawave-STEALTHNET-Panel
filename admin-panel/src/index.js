import React, { Suspense } from 'react'; // ❗️ Импорт Suspense
import ReactDOM from 'react-dom/client';
import './index.css';
import App from './App';
import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from './AuthContext';
import { ThemeProvider } from './ThemeContext'; 
import './i18n'; 

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  // ❗️❗️❗️ ВОТ ИСПРАВЛЕНИЕ: ❗️❗️❗️
  // Оборачиваем ВСЕ в <Suspense>, чтобы i18n успел загрузиться
  <Suspense fallback={<div className="loading-full">Загрузка...</div>}>
    <React.StrictMode>
      <BrowserRouter>
        <AuthProvider>
          <ThemeProvider>
            <App />
          </ThemeProvider>
        </AuthProvider>
      </BrowserRouter>
    </React.StrictMode>
  </Suspense>
);
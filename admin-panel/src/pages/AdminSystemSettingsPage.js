import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';

function AdminSystemSettingsPage() {
  const [settings, setSettings] = useState({
    default_language: 'ru',
    default_currency: 'uah'
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saveStatus, setSaveStatus] = useState(null);
  const { token } = useAuth();

  useEffect(() => {
    const fetchSettings = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch('/api/admin/system-settings', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error('Не удалось загрузить настройки');
        const data = await response.json();
        setSettings(data);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    
    if (token) {
      fetchSettings();
    }
  }, [token]);

  const handleChange = (field, value) => {
    setSettings(prev => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSaveStatus(null);
    
    try {
      const response = await fetch('/api/admin/system-settings', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(settings)
      });
      
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || 'Ошибка сохранения');
      
      setSaveStatus('success');
      setTimeout(() => setSaveStatus(null), 2000);
    } catch (e) {
      setError(e.message);
      setSaveStatus('error');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <main className="admin-page-content">
        <section><div className="loading-mini">Загрузка...</div></section>
      </main>
    );
  }

  return (
    <main className="admin-page-content">
      <section>
        <h2 className="admin-page-title">Системные настройки</h2>
        <p className="admin-description-text">
          Настройте язык и валюту по умолчанию для новых пользователей. Эти настройки будут применяться при регистрации.
        </p>
        
        {error && <div className="message-error">{error}</div>}
        
        <form onSubmit={handleSubmit}>
          <div className="settings-form-group">
            <label htmlFor="default_language" className="settings-label">
              Язык по умолчанию
            </label>
            <select
              id="default_language"
              value={settings.default_language}
              onChange={(e) => handleChange('default_language', e.target.value)}
              className="settings-select"
            >
              <option value="ru">Русский</option>
              <option value="ua">Українська</option>
              <option value="cn">中文</option>
              <option value="en">English</option>
            </select>
            <p className="settings-hint">Этот язык будет установлен для всех новых пользователей при регистрации.</p>
          </div>

          <div className="settings-form-group">
            <label htmlFor="default_currency" className="settings-label">
              Валюта по умолчанию
            </label>
            <select
              id="default_currency"
              value={settings.default_currency}
              onChange={(e) => handleChange('default_currency', e.target.value)}
              className="settings-select"
            >
              <option value="uah">₴ UAH (Гривна)</option>
              <option value="rub">₽ RUB (Рубль)</option>
              <option value="usd">$ USD (Доллар)</option>
            </select>
            <p className="settings-hint">Эта валюта будет установлена для всех новых пользователей при регистрации.</p>
          </div>
          
          <div className="settings-actions">
            <button 
              type="submit" 
              className="btn" 
              style={{ maxWidth: '200px' }}
              disabled={saving}
            >
              {saving ? 'Сохранение...' : 'Сохранить изменения'}
            </button>
            {saveStatus === 'success' && (
              <div className="message-success">Сохранено!</div>
            )}
          </div>
        </form>
      </section>
    </main>
  );
}

export default AdminSystemSettingsPage;


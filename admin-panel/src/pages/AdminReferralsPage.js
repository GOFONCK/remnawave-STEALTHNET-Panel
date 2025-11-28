import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';

function AdminReferralsPage() {
  const [settings, setSettings] = useState({
    invitee_bonus_days: 7,
    referrer_bonus_days: 7,
    trial_squad_id: ''
  });
  const [squads, setSquads] = useState([]);
  const [squadsLoading, setSquadsLoading] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saveStatus, setSaveStatus] = useState(null); // 'saving', 'success', 'error'
  const { token } = useAuth();
  
  // --- 1. Загрузка текущих настроек ---
  useEffect(() => {
    const fetchSettings = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch('/api/admin/referral-settings', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error('Не удалось загрузить настройки');
        const data = await response.json();
        setSettings({
          invitee_bonus_days: data.invitee_bonus_days || 7,
          referrer_bonus_days: data.referrer_bonus_days || 7,
          trial_squad_id: data.trial_squad_id || ''
        });
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

  // --- Загрузка сквадов ---
  useEffect(() => {
    const fetchSquads = async () => {
      setSquadsLoading(true);
      try {
        const response = await fetch('/api/admin/squads', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
          const data = await response.json();
          const squadsList = Array.isArray(data) ? data : [];
          setSquads(squadsList);
        }
      } catch (e) {
        console.error('Ошибка загрузки сквадов:', e);
      } finally {
        setSquadsLoading(false);
      }
    };
    
    if (token) {
      fetchSquads();
    }
  }, [token]);

  // --- 2. Обработчик изменения полей ---
  const handleChange = (e) => {
    const { name, value } = e.target;
    setSettings(prev => ({
      ...prev,
      [name]: name === 'trial_squad_id' ? value : parseInt(value, 10) // Для сквада оставляем строку, для дней - число
    }));
  };

  // --- 3. Сохранение настроек ---
  const handleSave = async (e) => {
    e.preventDefault();
    setSaveStatus('saving');
    setError(null);
    try {
      const response = await fetch('/api/admin/referral-settings', {
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
      setTimeout(() => setSaveStatus(null), 2000); // Показать "Сохранено!" на 2 сек

    } catch (e) {
      setError(e.message);
      setSaveStatus('error');
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
        <h2>Настройки реферальной программы</h2>
        <p className="admin-description-text">
          Здесь вы можете настроить, какие бонусы будут получать пользователи.
        </p>
        
        {error && <div className="message-error">{error}</div>}
        
        {/* Используем тот же CSS-класс, что и у тарифов */}
        <form className="tariff-form" onSubmit={handleSave}>
          <div className="form-row">
            <div className="form-group">
              <label>Бонус Приглашенному (Новому)</label>
              <input 
                type="number" 
                name="invitee_bonus_days"
                value={settings.invitee_bonus_days} 
                onChange={handleChange} 
                required 
              />
              <small>Сколько бесплатных дней получит новый пользователь, который регистрируется по реф. ссылке.</small>
            </div>
            <div className="form-group">
              <label>Бонус Пригласившему (Старому)</label>
              <input 
                type="number" 
                name="referrer_bonus_days"
                value={settings.referrer_bonus_days} 
                onChange={handleChange} 
                required 
              />
              <small>Сколько бесплатных дней получит владелец реф. ссылки.</small>
            </div>
          </div>
          
          <div className="form-row">
            <div className="form-group" style={{ flex: '1 1 100%' }}>
              <label>Сквад для триальной подписки</label>
              <select 
                name="trial_squad_id"
                value={settings.trial_squad_id || ''} 
                onChange={handleChange}
                disabled={squadsLoading}
                style={{ width: '100%' }}
              >
                <option value="">Не выбран (используется дефолтный из .env)</option>
                {squads.map(squad => (
                  <option key={squad.uuid || squad.id} value={squad.uuid || squad.id}>
                    {squad.name || squad.title || squad.uuid || squad.id}
                  </option>
                ))}
              </select>
              {squadsLoading && <small>Загрузка сквадов...</small>}
              <small>Сквад, который будет назначен пользователю при активации триальной подписки.</small>
            </div>
          </div>
          
          <div style={{display: 'flex', alignItems: 'center', gap: '20px'}}>
            <button 
              type="submit" 
              className="btn" 
              style={{maxWidth: '200px'}}
              disabled={saveStatus === 'saving'}
            >
              {saveStatus === 'saving' ? 'Сохранение...' : 'Сохранить настройки'}
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

export default AdminReferralsPage;
import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';

function AdminTariffFeaturesPage() {
  const [features, setFeatures] = useState({
    basic: ['Безлимитный трафик', 'До 5 устройств', 'Базовый анти-DPI'],
    pro: ['Приоритетная скорость', 'До 10 устройств', 'Ротация IP-адресов'],
    elite: ['VIP-поддержка 24/7', 'Статический IP по запросу', 'Автообновление ключей']
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [saveStatus, setSaveStatus] = useState(null);
  const { token } = useAuth();

  useEffect(() => {
    const fetchFeatures = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch('/api/admin/tariff-features', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error('Не удалось загрузить функции');
        const data = await response.json();
        setFeatures(data);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    
    if (token) {
      fetchFeatures();
    }
  }, [token]);

  const handleFeatureChange = (tier, index, value) => {
    setFeatures(prev => ({
      ...prev,
      [tier]: prev[tier].map((item, i) => i === index ? value : item)
    }));
  };

  const handleAddFeature = (tier) => {
    setFeatures(prev => ({
      ...prev,
      [tier]: [...prev[tier], '']
    }));
  };

  const handleRemoveFeature = (tier, index) => {
    setFeatures(prev => ({
      ...prev,
      [tier]: prev[tier].filter((_, i) => i !== index)
    }));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSaveStatus(null);
    
    try {
      const response = await fetch('/api/admin/tariff-features', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(features)
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

  const tierLabels = {
    basic: { name: 'Basic (Базовый)', color: 'var(--accent-primary)' },
    pro: { name: 'Pro (Премиум)', color: 'var(--accent-orange)' },
    elite: { name: 'Elite (Элитный)', color: 'var(--accent-purple)' }
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
        <h2 className="admin-page-title">Настройка функций тарифов</h2>
        <p className="admin-description-text">
          Здесь вы можете настроить список функций, которые отображаются для каждого уровня тарифа (basic, pro, elite).
        </p>
        
        {error && <div className="message-error">{error}</div>}
        
        <form onSubmit={handleSave}>
          {Object.keys(features).map(tier => (
            <div key={tier} className="tariff-feature-tier-card">
              <h3 className="tariff-feature-tier-title" style={{ color: tierLabels[tier].color }}>
                <span className="tier-indicator" style={{ background: tierLabels[tier].color }}></span>
                {tierLabels[tier].name}
              </h3>
              
              <div className="tariff-feature-list">
                {features[tier].map((feature, index) => (
                  <div key={index} className="tariff-feature-item">
                    <input
                      type="text"
                      value={feature}
                      onChange={(e) => handleFeatureChange(tier, index, e.target.value)}
                      className="tariff-feature-input"
                      placeholder={`Функция ${index + 1}`}
                    />
                    <button
                      type="button"
                      onClick={() => handleRemoveFeature(tier, index)}
                      className="btn-table-delete"
                      disabled={features[tier].length <= 1}
                    >
                      Удалить
                    </button>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => handleAddFeature(tier)}
                  className="btn"
                  style={{ maxWidth: '200px', marginTop: '10px' }}
                >
                  + Добавить функцию
                </button>
              </div>
            </div>
          ))}
          
          <div className="tariff-feature-actions">
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

export default AdminTariffFeaturesPage;


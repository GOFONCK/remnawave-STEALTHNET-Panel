import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';

function AdminTariffsPage() {
  const [tariffs, setTariffs] = useState([]);
  const [squads, setSquads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [squadsLoading, setSquadsLoading] = useState(true);
  const [error, setError] = useState(null);
  const { token } = useAuth();
  
  const [name, setName] = useState('');
  const [days, setDays] = useState(30);
  const [priceUAH, setPriceUAH] = useState(0);
  const [priceRUB, setPriceRUB] = useState(0);
  const [priceUSD, setPriceUSD] = useState(0);
  const [selectedSquadId, setSelectedSquadId] = useState('');
  const [trafficLimitGB, setTrafficLimitGB] = useState(0);
  const [selectedTier, setSelectedTier] = useState('');
  const [badge, setBadge] = useState('');
  
  // Состояние для редактирования
  const [editingTariff, setEditingTariff] = useState(null);
  const [editName, setEditName] = useState('');
  const [editDays, setEditDays] = useState(30);
  const [editPriceUAH, setEditPriceUAH] = useState(0);
  const [editPriceRUB, setEditPriceRUB] = useState(0);
  const [editPriceUSD, setEditPriceUSD] = useState(0);
  const [editSelectedSquadId, setEditSelectedSquadId] = useState('');
  const [editTrafficLimitGB, setEditTrafficLimitGB] = useState(0);
  const [editSelectedTier, setEditSelectedTier] = useState('');
  const [editBadge, setEditBadge] = useState('');
  
  // Загрузка тарифов
  useEffect(() => {
    const fetchTariffs = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch('/api/admin/tariffs', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error('Не удалось загрузить тарифы');
        const data = await response.json();
        setTariffs(data);
      } catch (e) { setError(e.message); } 
      finally { setLoading(false); }
    };
    
    if (token) {
        fetchTariffs();
    }
  }, [token]);

  // Загрузка сквадов
  useEffect(() => {
    const fetchSquads = async () => {
      setSquadsLoading(true);
      try {
        const response = await fetch('/api/admin/squads', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
          const data = await response.json();
          // Backend уже обработал структуру и вернул массив
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

  // --- Создание тарифа ---
  const handleCreateTariff = async (e) => {
    e.preventDefault();
    try {
      // Конвертируем гигабайты в байты (1 GB = 1073741824 bytes)
      const trafficLimitBytes = trafficLimitGB > 0 ? Math.round(trafficLimitGB * 1073741824) : 0;
      
      const response = await fetch('/api/admin/tariffs', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: name,
          duration_days: days,
          price_uah: priceUAH,
          price_rub: priceRUB,
          price_usd: priceUSD,
          squad_id: selectedSquadId || null,
          traffic_limit_bytes: trafficLimitBytes,
          tier: selectedTier || null,
          badge: badge || null
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || 'Ошибка создания');
      
      setName(''); setDays(30); setPriceUAH(0); setPriceRUB(0); setPriceUSD(0); setSelectedSquadId(''); setTrafficLimitGB(0); setSelectedTier(''); setBadge('');
      // ❗️ ИЗМЕНЕНИЕ: Обновляем список вручную
      setTariffs(prev => [...prev, data.response || data]);
      
    } catch (e) { alert(e.message); }
  };
  
  // --- Открытие формы редактирования ---
  const handleEditTariff = (tariff) => {
    setEditingTariff(tariff);
    setEditName(tariff.name || '');
    setEditDays(tariff.duration_days || 30);
    setEditPriceUAH(tariff.price_uah || 0);
    setEditPriceRUB(tariff.price_rub || 0);
    setEditPriceUSD(tariff.price_usd || 0);
    setEditSelectedSquadId(tariff.squad_id || '');
    setEditTrafficLimitGB(tariff.traffic_limit_bytes ? (tariff.traffic_limit_bytes / 1073741824) : 0);
    setEditSelectedTier(tariff.tier || '');
    setEditBadge(tariff.badge || '');
  };
  
  // --- Закрытие формы редактирования ---
  const handleCloseEdit = () => {
    setEditingTariff(null);
    setEditName('');
    setEditDays(30);
    setEditPriceUAH(0);
    setEditPriceRUB(0);
    setEditPriceUSD(0);
    setEditSelectedSquadId('');
    setEditTrafficLimitGB(0);
    setEditSelectedTier('');
    setEditBadge('');
  };
  
  // --- Обновление тарифа ---
  const handleUpdateTariff = async (e) => {
    e.preventDefault();
    if (!editingTariff) return;
    
    try {
      const trafficLimitBytes = editTrafficLimitGB > 0 ? Math.round(editTrafficLimitGB * 1073741824) : 0;
      
      const response = await fetch(`/api/admin/tariffs/${editingTariff.id}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          name: editName,
          duration_days: editDays,
          price_uah: editPriceUAH,
          price_rub: editPriceRUB,
          price_usd: editPriceUSD,
          squad_id: editSelectedSquadId || null,
          traffic_limit_bytes: trafficLimitBytes,
          tier: editSelectedTier || null,
          badge: editBadge || null
        })
      });
      
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || 'Ошибка обновления');
      
      // Обновляем список тарифов
      setTariffs(prev => prev.map(t => 
        t.id === editingTariff.id 
          ? { ...t, ...data.response, name: editName, duration_days: editDays, price_uah: editPriceUAH, price_rub: editPriceRUB, price_usd: editPriceUSD, squad_id: editSelectedSquadId || null, traffic_limit_bytes: trafficLimitBytes, tier: editSelectedTier || null, badge: editBadge || null }
          : t
      ));
      
      handleCloseEdit();
    } catch (e) { 
      alert(e.message); 
    }
  };
  
  // --- Удаление тарифа ---
  const handleDeleteTariff = async (tariffId) => {
    if (!window.confirm("Удалить этот тариф?")) return;
    try {
       const response = await fetch(`/api/admin/tariffs/${tariffId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) throw new Error('Ошибка удаления');
      // ❗️ ИЗМЕНЕНИЕ: Обновляем список вручную
      setTariffs(prev => prev.filter(t => t.id !== tariffId));
    } catch (e) { alert(e.message); }
  };

  return (
    <main className="admin-page-content">
      {/* Секция 1: Форма создания */}
      <section>
        <h2>Создать новый тариф</h2>
        <form className="tariff-form" onSubmit={handleCreateTariff}>
          {/* ... (весь JSX формы без изменений) ... */}
          <div className="form-row">
            <div className="form-group">
              <label>Название (н.п. "1 Месяц")</label>
              <input type="text" value={name} onChange={e => setName(e.target.value)} required />
            </div>
            <div className="form-group">
              <label>Длительность (в днях)</label>
              <input type="number" value={days} onChange={e => setDays(e.target.value)} required />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Цена (UAH)</label>
              <input type="number" value={priceUAH} onChange={e => setPriceUAH(e.target.value)} required />
            </div>
            <div className="form-group">
              <label>Цена (RUB)</label>
              <input type="number" value={priceRUB} onChange={e => setPriceRUB(e.target.value)} required />
            </div>
            <div className="form-group">
              <label>Цена (USD)</label>
              <input type="number" value={priceUSD} onChange={e => setPriceUSD(e.target.value)} required />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group" style={{ flex: '1 1 100%' }}>
              <label>Сквад (опционально)</label>
              <select 
                value={selectedSquadId} 
                onChange={e => setSelectedSquadId(e.target.value)}
                disabled={squadsLoading}
                style={{ width: '100%' }}
              >
                <option value="">Не выбран (используется дефолтный)</option>
                {squads.map(squad => (
                  <option key={squad.uuid || squad.id} value={squad.uuid || squad.id}>
                    {squad.name || squad.title || squad.uuid || squad.id}
                  </option>
                ))}
              </select>
              {squadsLoading && <small>Загрузка сквадов...</small>}
              {!squadsLoading && squads.length === 0 && (
                <small style={{ color: 'var(--accent-orange)' }}>
                  Сквады не загружены. Проверьте настройки API в разделе "Сквады".
                </small>
              )}
            </div>
          </div>
          <div className="form-row">
            <div className="form-group" style={{ flex: '1 1 100%' }}>
              <label>Лимит трафика (в гигабайтах)</label>
              <input 
                type="number" 
                value={trafficLimitGB} 
                onChange={e => setTrafficLimitGB(e.target.value || 0)} 
                min="0"
                step="0.1"
                placeholder="0 = безлимит"
              />
              <small>
                Укажите лимит трафика в гигабайтах. 0 = безлимит. 
                Примеры: 1 (1 GB), 10 (10 GB), 50 (50 GB)
              </small>
            </div>
          </div>
          <div className="form-row">
            <div className="form-group" style={{ flex: '1 1 100%' }}>
              <label>Уровень тарифа (опционально)</label>
              <select 
                value={selectedTier} 
                onChange={e => setSelectedTier(e.target.value)}
                style={{ width: '100%' }}
              >
                <option value="">Автоматически (по длительности)</option>
                <option value="basic">Basic (Базовый)</option>
                <option value="pro">Pro (Премиум)</option>
                <option value="elite">Elite (Элитный)</option>
              </select>
              <small>
                Если не выбран, уровень определяется автоматически: &lt;90 дней = basic, 90-179 дней = pro, ≥180 дней = elite
              </small>
            </div>
            <div className="form-group" style={{ flex: '1 1 100%' }}>
              <label>Бейдж (опционально)</label>
              <select 
                value={badge} 
                onChange={e => setBadge(e.target.value)}
                style={{ width: '100%' }}
              >
                <option value="">Без бейджа</option>
                <option value="top_sale">ТОП продаж</option>
              </select>
              <small>Выберите бейдж для отображения на тарифе</small>
            </div>
          </div>
          <button type="submit" className="btn" style={{maxWidth: '200px'}}>Создать тариф</button>
        </form>
      </section>
      
      {/* Секция 2: Список тарифов */}
      <section>
        <h2>Текущие тарифы</h2>
        {loading && <div className="loading-mini">Загрузка...</div>}
        {error && <div className="message-error">{error}</div>}
        
        {!loading && !error && (
          <div className="table-wrapper">
            <table className="users-table">
              {/* ... (вся таблица <thead> и <tbody> без изменений) ... */}
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Название</th>
                  <th>Дни</th>
                  <th>UAH</th>
                  <th>RUB</th>
                  <th>USD</th>
                  <th>Сквад</th>
                  <th>Лимит трафика</th>
                  <th>Уровень</th>
                  <th>Бейдж</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {tariffs.map(t => {
                  const squad = squads.find(s => (s.uuid || s.id) === t.squad_id);
                  return (
                    <tr key={t.id}>
                      <td>{t.id}</td>
                      <td>{t.name}</td>
                      <td>{t.duration_days}</td>
                      <td>{t.price_uah}</td>
                      <td>{t.price_rub}</td>
                      <td>{t.price_usd}</td>
                      <td>
                        {t.squad_id ? (
                          <span className="code-cell" title={squad ? squad.name || squad.title : t.squad_id}>
                            {squad ? (squad.name || squad.title) : t.squad_id.substring(0, 8) + '...'}
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-secondary)' }}>Дефолтный</span>
                        )}
                      </td>
                      <td>
                        {t.traffic_limit_bytes && t.traffic_limit_bytes > 0 ? (
                          <span title={`${t.traffic_limit_bytes} байт`}>
                            {(t.traffic_limit_bytes / 1073741824).toFixed(1)} GB
                          </span>
                        ) : (
                          <span style={{ color: 'var(--accent-primary)' }}>Безлимит</span>
                        )}
                      </td>
                      <td>
                        {t.tier ? (
                          <span className={`role-badge role-${t.tier}`} style={{ textTransform: 'capitalize' }}>
                            {t.tier}
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>Авто</span>
                        )}
                      </td>
                      <td>
                        {t.badge ? (
                          <span className="role-badge" style={{ background: 'var(--accent-yellow)', color: '#1f2933', textTransform: 'uppercase', fontSize: '11px' }}>
                            {t.badge === 'top_sale' ? 'ТОП продаж' : t.badge}
                          </span>
                        ) : (
                          <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>—</span>
                        )}
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                          <button 
                            className="btn-table-edit"
                            onClick={() => handleEditTariff(t)}
                            style={{ padding: '6px 12px', fontSize: '13px' }}
                          >
                            Редактировать
                          </button>
                          <button 
                            className="btn-table-delete"
                            onClick={() => handleDeleteTariff(t.id)}
                          >
                            Удалить
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      
      {/* Модальное окно редактирования */}
      {editingTariff && (
        <div className="modal-overlay" onClick={handleCloseEdit}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Редактировать тариф</h2>
              <button className="modal-close" onClick={handleCloseEdit}>×</button>
            </div>
            <form className="tariff-form" onSubmit={handleUpdateTariff}>
              <div className="form-row">
                <div className="form-group">
                  <label>Название (н.п. "1 Месяц")</label>
                  <input 
                    type="text" 
                    value={editName} 
                    onChange={e => setEditName(e.target.value)} 
                    required 
                  />
                </div>
                <div className="form-group">
                  <label>Длительность (в днях)</label>
                  <input 
                    type="number" 
                    value={editDays} 
                    onChange={e => setEditDays(e.target.value)} 
                    required 
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Цена (UAH)</label>
                  <input 
                    type="number" 
                    value={editPriceUAH} 
                    onChange={e => setEditPriceUAH(e.target.value)} 
                    required 
                  />
                </div>
                <div className="form-group">
                  <label>Цена (RUB)</label>
                  <input 
                    type="number" 
                    value={editPriceRUB} 
                    onChange={e => setEditPriceRUB(e.target.value)} 
                    required 
                  />
                </div>
                <div className="form-group">
                  <label>Цена (USD)</label>
                  <input 
                    type="number" 
                    value={editPriceUSD} 
                    onChange={e => setEditPriceUSD(e.target.value)} 
                    required 
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group" style={{ flex: '1 1 100%' }}>
                  <label>Сквад (опционально)</label>
                  <select 
                    value={editSelectedSquadId} 
                    onChange={e => setEditSelectedSquadId(e.target.value)}
                    disabled={squadsLoading}
                    style={{ width: '100%' }}
                  >
                    <option value="">Не выбран (используется дефолтный)</option>
                    {squads.map(squad => (
                      <option key={squad.uuid || squad.id} value={squad.uuid || squad.id}>
                        {squad.name || squad.title || squad.uuid || squad.id}
                      </option>
                    ))}
                  </select>
                  {squadsLoading && <small>Загрузка сквадов...</small>}
                  {!squadsLoading && squads.length === 0 && (
                    <small style={{ color: 'var(--accent-orange)' }}>
                      Сквады не загружены. Проверьте настройки API в разделе "Сквады".
                    </small>
                  )}
                </div>
              </div>
              <div className="form-row">
                <div className="form-group" style={{ flex: '1 1 100%' }}>
                  <label>Лимит трафика (в гигабайтах)</label>
                  <input 
                    type="number" 
                    value={editTrafficLimitGB} 
                    onChange={e => setEditTrafficLimitGB(e.target.value || 0)} 
                    min="0"
                    step="0.1"
                    placeholder="0 = безлимит"
                  />
                  <small>
                    Укажите лимит трафика в гигабайтах. 0 = безлимит. 
                    Примеры: 1 (1 GB), 10 (10 GB), 50 (50 GB)
                  </small>
                </div>
              </div>
              <div className="form-row">
                <div className="form-group" style={{ flex: '1 1 100%' }}>
                  <label>Уровень тарифа (опционально)</label>
                  <select 
                    value={editSelectedTier} 
                    onChange={e => setEditSelectedTier(e.target.value)}
                    style={{ width: '100%' }}
                  >
                    <option value="">Автоматически (по длительности)</option>
                    <option value="basic">Basic (Базовый)</option>
                    <option value="pro">Pro (Премиум)</option>
                    <option value="elite">Elite (Элитный)</option>
                  </select>
                  <small>
                    Если не выбран, уровень определяется автоматически: &lt;90 дней = basic, 90-179 дней = pro, ≥180 дней = elite
                  </small>
                </div>
                <div className="form-group" style={{ flex: '1 1 100%' }}>
                  <label>Бейдж (опционально)</label>
                  <select 
                    value={editBadge} 
                    onChange={e => setEditBadge(e.target.value)}
                    style={{ width: '100%' }}
                  >
                    <option value="">Без бейджа</option>
                    <option value="top_sale">ТОП продаж</option>
                  </select>
                  <small>Выберите бейдж для отображения на тарифе</small>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
                <button type="submit" className="btn">Сохранить изменения</button>
                <button type="button" className="btn btn-secondary" onClick={handleCloseEdit}>Отмена</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}

export default AdminTariffsPage;
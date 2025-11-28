import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';

function AdminPromoCodesPage() {
  const [promoCodes, setPromoCodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { token } = useAuth();
  
  // Cостояния для НОВОГО кода
  const [code, setCode] = useState('');
  const [promoType, setPromoType] = useState('PERCENT');
  const [value, setValue] = useState(10);
  const [usesLeft, setUsesLeft] = useState(1);
  
  // ❗️ ИЗМЕНЕНИЕ: fetchPromoCodes теперь объявлен ВНУТРИ useEffect
  useEffect(() => {
    const fetchPromoCodes = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch('/api/admin/promocodes', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error('Не удалось загрузить промокоды');
        const data = await response.json();
        setPromoCodes(data);
      } catch (e) { setError(e.message); } 
      finally { setLoading(false); }
    };

    if (token) {
        fetchPromoCodes();
    }
  }, [token]); // ❗️ Теперь массив зависимостей правильный

  // --- Создание кода ---
  const handleCreateCode = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch('/api/admin/promocodes', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          code: code,
          promo_type: promoType,
          value: value,
          uses_left: usesLeft
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || 'Ошибка создания');
      
      setCode(''); setPromoType('PERCENT'); setValue(10); setUsesLeft(1);
      
      // Добавляем новый код в список
      if (data.response) {
        setPromoCodes(prev => [...prev, data.response]);
      } else {
        // Если ответ не содержит response, перезагружаем список
        const fetchResponse = await fetch('/api/admin/promocodes', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (fetchResponse.ok) {
          const fetchData = await fetchResponse.json();
          setPromoCodes(fetchData);
        }
      } 
      
    } catch (e) { alert(e.message); }
  };
  
  // --- Удаление кода ---
  const handleDeleteCode = async (codeId) => {
    if (!window.confirm("Удалить этот промокод?")) return;
    try {
       const response = await fetch(`/api/admin/promocodes/${codeId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) throw new Error('Ошибка удаления');
      // ❗️ ИЗМЕНЕНИЕ: Просто фильтруем список
      setPromoCodes(prev => prev.filter(c => c.id !== codeId)); 
    } catch (e) { alert(e.message); }
  };

  return (
    <main className="admin-page-content">
      {/* Секция 1: Форма создания */}
      <section>
        <h2>Создать новый промокод</h2>
        <form className="tariff-form" onSubmit={handleCreateCode}>
          {/* ... (весь JSX формы без изменений) ... */}
          <div className="form-row">
            <div className="form-group">
              <label>Код (н.п. "SALE2025")</label>
              <input type="text" value={code} onChange={e => setCode(e.target.value.toUpperCase())} required />
            </div>
            <div className="form-group">
              <label>Кол-во использований</label>
              <input type="number" value={usesLeft} onChange={e => setUsesLeft(e.target.value)} required />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Тип</label>
              <select value={promoType} onChange={e => setPromoType(e.target.value)}>
                <option value="PERCENT">Скидка (%)</option>
                <option value="DAYS">Бесплатные дни</option>
              </select>
            </div>
            <div className="form-group">
              <label>{promoType === 'PERCENT' ? 'Размер скидки (%)' : 'Кол-во дней'}</label>
              <input type="number" value={value} onChange={e => setValue(e.target.value)} required />
            </div>
          </div>
          <button type="submit" className="btn" style={{maxWidth: '200px'}}>Создать промокод</button>
        </form>
      </section>
      
      {/* Секция 2: Список промокодов */}
      <section>
        <h2>Текущие промокоды</h2>
        {loading && <div className="loading-mini">Загрузка...</div>}
        {error && <div className="message-error">{error}</div>}
        
        {!loading && !error && (
          <div className="table-wrapper">
            <table className="users-table">
              {/* ... (вся таблица <thead> и <tbody> без изменений) ... */}
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Код</th>
                  <th>Тип</th>
                  <th>Значение</th>
                  <th>Осталось использований</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {promoCodes.map(c => (
                  <tr key={c.id}>
                    <td>{c.id}</td>
                    <td><strong className="code-cell">{c.code}</strong></td>
                    <td>{c.promo_type === 'PERCENT' ? 'Скидка' : 'Бесп. дни'}</td>
                    <td>{c.promo_type === 'PERCENT' ? `${c.value}%` : `${c.value} д.`}</td>
                    <td>{c.uses_left}</td>
                    <td>
                      <button 
                        className="btn-table-delete"
                        onClick={() => handleDeleteCode(c.id)}
                      >
                        Удалить
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

export default AdminPromoCodesPage;
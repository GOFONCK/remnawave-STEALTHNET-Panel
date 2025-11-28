import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../AuthContext';
import { LuServer, LuRefreshCw } from 'react-icons/lu';

function AdminSquadsPage() {
  const [squads, setSquads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const { token } = useAuth();

  const fetchSquads = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const response = await fetch('/api/admin/squads', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.message || 'Не удалось загрузить сквады');
      }
      const data = await response.json();
      // Обрабатываем ответ - API возвращает массив сквадов напрямую
      // (backend уже обработал структуру response.internalSquads)
      const squadsList = Array.isArray(data) ? data : [];
      setSquads(squadsList);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [token]);

  useEffect(() => {
    if (token) {
      fetchSquads();
    }
  }, [token, fetchSquads]);

  const handleRefresh = () => {
    fetchSquads();
  };

  return (
    <main className="admin-page-content">
      <section>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <h2>Управление сквадами</h2>
          <button 
            className="btn" 
            onClick={handleRefresh}
            disabled={refreshing}
            style={{ display: 'flex', alignItems: 'center', gap: '8px' }}
          >
            <LuRefreshCw style={{ animation: refreshing ? 'spin 1s linear infinite' : 'none' }} />
            Обновить
          </button>
        </div>

        <p className="admin-description-text">
          Здесь отображаются все доступные сквады из внешнего API. Вы можете выбрать сквад для каждого тарифа в разделе "Тарифы".
        </p>

        {loading && <div className="loading-mini">Загрузка сквадов...</div>}
        {error && <div className="message-error">{error}</div>}

        {!loading && !error && (
          <>
            {squads.length === 0 ? (
              <div className="loading-mini">Сквады не найдены</div>
            ) : (
              <div className="squads-grid">
                {squads.map((squad, index) => (
                  <div key={squad.uuid || squad.id || index} className="squad-card">
                    <div className="squad-card-header">
                      <div className="squad-icon">
                        <LuServer />
                      </div>
                      <div className="squad-info">
                        <h3 className="squad-name">{squad.name || squad.title || 'Без названия'}</h3>
                        {squad.description && (
                          <p className="squad-description">{squad.description}</p>
                        )}
                      </div>
                    </div>
                    <div className="squad-details">
                      <div className="squad-detail-item">
                        <span className="squad-label">UUID:</span>
                        <span className="squad-value code-cell">{squad.uuid || 'N/A'}</span>
                      </div>
                      {squad.info && (
                        <>
                          {squad.info.membersCount !== undefined && (
                            <div className="squad-detail-item">
                              <span className="squad-label">Участников:</span>
                              <span className="squad-value">{squad.info.membersCount}</span>
                            </div>
                          )}
                          {squad.info.inboundsCount !== undefined && (
                            <div className="squad-detail-item">
                              <span className="squad-label">Inbounds:</span>
                              <span className="squad-value">{squad.info.inboundsCount}</span>
                            </div>
                          )}
                        </>
                      )}
                      {squad.inbounds && Array.isArray(squad.inbounds) && (
                        <div className="squad-detail-item">
                          <span className="squad-label">Inbounds:</span>
                          <span className="squad-value">{squad.inbounds.length}</span>
                        </div>
                      )}
                      {squad.createdAt && (
                        <div className="squad-detail-item">
                          <span className="squad-label">Создан:</span>
                          <span className="squad-value">
                            {new Date(squad.createdAt).toLocaleDateString('ru-RU')}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </section>
    </main>
  );
}

export default AdminSquadsPage;


import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';
import { LuUsers, LuWallet, LuChartBar, LuActivity, LuServer } from 'react-icons/lu';
import { Link } from 'react-router-dom'; // ❗️ Для ссылки на "всех пользователей"

// --- Компонент: Карточка статистики (Виджет) ---
// (Внес небольшие изменения в formatValue для .toFixed(2))
const StatCard = ({ title, value, icon, currency = '' }) => {
  const formatValue = (val) => {
    const numValue = parseFloat(val);
    if (isNaN(numValue)) return val;
    
    // Если это целое число (напр. 10 пользователей)
    if (numValue % 1 === 0) {
        if (numValue >= 1000) return `${(numValue / 1000).toFixed(1)}k`;
        return numValue;
    }
    // Если это деньги (напр. 100.50)
    return numValue.toFixed(2);
  };
  
  return (
    <div className="stat-card">
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', width: '100%' }}>
        <div className="stat-icon">
          {icon}
        </div>
        <div className="stat-content">
          <h3 className="stat-title">{title}</h3>
          <div className="stat-value">
            {currency}{formatValue(value)}
          </div>
        </div>
      </div>
    </div>
  );
};

// --- ❗️ НОВЫЙ КОМПОНЕНТ: Виджет "Последние пользователи" ---
const RecentUsersWidget = ({ users }) => {
    // Берем 5 последних пользователей
    const recentUsers = users.slice(0, 5);

    return (
        <div className="widget-card">
            <h3 className="widget-title">Последние регистрации</h3>
            <div className="widget-content">
                {recentUsers.length === 0 && <div className="loading-mini">Нет пользователей...</div>}
                <ul className="user-widget-list">
                    {recentUsers.map(user => (
                        <li key={user.id} className="user-widget-item">
                            <span className="user-widget-email">{user.email}</span>
                            <span className={`role-badge role-${user.role}`}>{user.role}</span>
                        </li>
                    ))}
                </ul>
                <Link to="/admin/users" className="widget-footer-link">
                    Показать всех &rarr;
                </Link>
            </div>
        </div>
    );
};

// --- ❗️ НОВЫЙ КОМПОНЕНТ: Виджет "Сквады" ---
const SquadsWidget = ({ squads, loading }) => {
    return (
        <div className="widget-card">
            <h3 className="widget-title">Сквады</h3>
            <div className="widget-content">
                {loading && <div className="loading-mini">Загрузка...</div>}
                {!loading && squads.length === 0 && (
                    <div className="loading-mini">Сквады не найдены</div>
                )}
                {!loading && squads.length > 0 && (
                    <>
                        <div className="squads-widget-list">
                            {squads.slice(0, 5).map((squad, index) => (
                                <div key={squad.uuid || squad.id || index} className="squad-widget-item">
                                    <div className="squad-widget-icon">
                                        <LuServer />
                                    </div>
                                    <div className="squad-widget-info">
                                        <span className="squad-widget-name">
                                            {squad.name || squad.title || 'Без названия'}
                                        </span>
                                        <span className="squad-widget-uuid">
                                            {squad.uuid ? squad.uuid.substring(0, 12) + '...' : 'N/A'}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <Link to="/admin/squads" className="widget-footer-link">
                            Управление сквадами &rarr;
                        </Link>
                    </>
                )}
            </div>
        </div>
    );
};


// --- Основная страница Дашборда ---
function AdminDashboardPage() {
  const [stats, setStats] = useState(null);
  const [users, setUsers] = useState([]);
  const [squads, setSquads] = useState([]);
  const [squadsLoading, setSquadsLoading] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { token } = useAuth();

  useEffect(() => {
    const fetchAllData = async () => {
      setLoading(true);
      setError(null);
      try {
        // Запускаем запросы параллельно
        const [statsResponse, usersResponse] = await Promise.all([
          fetch('/api/admin/statistics', {
            headers: { 'Authorization': `Bearer ${token}` }
          }),
          fetch('/api/admin/users', {
            headers: { 'Authorization': `Bearer ${token}` }
          })
        ]);

        if (!statsResponse.ok) throw new Error('Не удалось загрузить статистику');
        if (!usersResponse.ok) throw new Error('Не удалось загрузить пользователей');

        const statsData = await statsResponse.json();
        const usersData = await usersResponse.json();
        
        setStats(statsData);
        setUsers(usersData.sort((a, b) => b.id - a.id)); 
        
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    if (token) {
      fetchAllData();
    }
  }, [token]);

  // Загрузка сквадов отдельно
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

  if (loading) return <main className="admin-page-content"><div className="loading-mini">Загрузка дашборда...</div></main>;
  if (error) return <main className="admin-page-content"><div className="message-error">{error}</div></main>;
  if (!stats) return <main className="admin-page-content"><div className="loading-mini">Нет данных.</div></main>;

  // (Логика подсчета та же)
  const totalUAH = stats.total_revenue?.UAH || 0;
  const totalRUB = stats.total_revenue?.RUB || 0;
  const totalUSD = stats.total_revenue?.USD || 0;
  const todayUAH = stats.today_revenue?.UAH || 0;
  const todayRUB = stats.today_revenue?.RUB || 0;
  const todayUSD = stats.today_revenue?.USD || 0;

  return (
    <main className="admin-page-content">
      {/* ❗️❗️❗️ НОВЫЙ МАКЕТ С КОЛОНКАМИ ❗️❗️❗️ */}
      <div className="dashboard-grid-layout">
        
        {/* --- 1. Основная колонка (Статистика) --- */}
        <div className="main-column">
          <section>
            <h2>Дашборд</h2>
            
            <h3>Общая статистика</h3>
            <div className="stats-grid">
              <StatCard title="Всего пользователей" value={stats.total_users || 0} icon={<LuUsers />} />
              <StatCard title="Всего продаж" value={stats.total_sales_count || 0} icon={<LuChartBar />} />
              <StatCard title="Прибыль (USD)" value={totalUSD} currency="$" icon={<LuWallet />} />
              <StatCard title="Прибыль (UAH)" value={totalUAH} currency="₴" icon={<LuWallet />} />
              <StatCard title="Прибыль (RUB)" value={totalRUB} currency="₽" icon={<LuWallet />} />
            </div>
            
            <h3 style={{marginTop: '30px'}}>За сегодня</h3>
            <div className="stats-grid stats-grid-today">
               <StatCard title="Прибыль сегодня (USD)" value={todayUSD} currency="$" icon={<LuActivity />} />
               <StatCard title="Прибыль сегодня (UAH)" value={todayUAH} currency="₴" icon={<LuActivity />} />
               <StatCard title="Прибыль сегодня (RUB)" value={todayRUB} currency="₽" icon={<LuActivity />} />
            </div>
          </section>
        </div>
        
        {/* --- 2. Боковая колонка (Виджеты) --- */}
        <div className="sidebar-column">
            <RecentUsersWidget users={users} />
            <SquadsWidget squads={squads} loading={squadsLoading} />
        </div>
        
      </div>
    </main>
  );
}

export default AdminDashboardPage;
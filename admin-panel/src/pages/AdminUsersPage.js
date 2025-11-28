import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';
// ❗️ ИЗМЕНЕНИЕ: Убрали 'Link'
// import { Link } from 'react-router-dom'; 

function AdminUsersPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { token } = useAuth(); 

  // ❗️ ИЗМЕНЕНИЕ: fetchUsers теперь ВНУТРИ useEffect
  useEffect(() => {
    const fetchUsers = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch('/api/admin/users', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.message || 'Не удалось получить список');
        }
        const data = await response.json();
        setUsers(data); 
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };

    if (token) {
        fetchUsers();
    }
  }, [token]); // ❗️ Теперь массив зависимостей правильный

  // --- Функция удаления ---
  const handleDeleteUser = async (userId, userEmail) => {
    if (!window.confirm(`Вы уверены, что хотите удалить ${userEmail}?`)) {
      return;
    }
    try {
      const response = await fetch(`/api/admin/users/${userId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await response.json(); 
      if (!response.ok) {
        throw new Error(data.message || 'Ошибка удаления');
      }
      // ❗️ ИЗМЕНЕНИЕ: Обновляем список вручную
      setUsers(prevUsers => prevUsers.filter(user => user.id !== userId));
      alert(data.message); 
    } catch (e) {
      alert(`Ошибка: ${e.message}`);
    }
  };

  // --- Форматирование даты (без изменений) ---
  const formatExpireDate = (dateString) => {
    if (!dateString) return { text: "N/A", isExpired: false };
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return { text: "N/A", isExpired: false };
    const isExpired = date < new Date();
    const formatted = date.toLocaleDateString('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
    return { text: formatted, isExpired: isExpired };
  };

  // --- Рендеринг ---
  return (
    <main className="admin-page-content">
      <section>
        <h2>Управление пользователями</h2>
        
        {loading && <div className="loading-mini">Загрузка...</div>}
        {error && <div className="message-error">{error}</div>}
        
        {!loading && !error && (
          <div className="table-wrapper">
            <table className="users-table">
              {/* ... (вся таблица <thead> и <tbody> без изменений) ... */}
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Статус (Live)</th>
                  <th>Сквад (Live)</th>
                  <th>Подписка до (Live)</th>
                  <th>Реф. Код</th>
                  <th>Приглашен (ID)</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {users.map(user => {
                  const liveData = user.live_data ? user.live_data.response : null;
                  let status = "N/A", expireAt = { text: "N/A", isExpired: false }, squadName = "N/A";
                  if (user.fetch_error) { status = "Ошибка"; } 
                  else if (liveData) {
                    status = liveData.status;
                    expireAt = formatExpireDate(liveData.expireAt);
                    const squad = liveData.activeInternalSquads && liveData.activeInternalSquads[0];
                    squadName = squad ? squad.name : "Нет";
                  }
                  return (
                    <tr key={user.id}>
                      <td>{user.id}</td>
                      <td title={user.email}>{user.email}</td>
                      <td><span className={`role-badge role-${user.role}`}>{user.role}</span></td>
                      <td><span className={`status-badge status-${status}`}>{status}</span></td>
                      <td>{squadName}</td>
                      <td className={expireAt.isExpired ? 'expired-cell' : ''}>{expireAt.text}</td>
                      <td className="code-cell">{user.referral_code || 'N/A'}</td>
                      <td>{user.referrer_id || 'N/A'}</td>
                      <td>
                        <button 
                          className="btn-table-delete"
                          onClick={() => handleDeleteUser(user.id, user.email)}
                        >
                          Удалить
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}

export default AdminUsersPage;
import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../AuthContext';
import { useParams, useNavigate } from 'react-router-dom';
import { LuSend } from 'react-icons/lu';
// ❗️❗️❗️ ИСПРАВЛЕНИЕ: Указываем правильный путь к CSS ❗️❗️❗️
import './client/SupportChat.css'; 

// ---------------------------------
// ❗️ КОМПОНЕНТ "ИНТЕРФЕЙС ЧАТА" ❗️
// ---------------------------------
const AdminChatInterface = ({ ticketId, token, onStatusChange }) => {
  const [ticket, setTicket] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState('');
  const { user } = useAuth(); // Мы используем 'user', чтобы знать ID админа

  // --- 1. Загрузка сообщений чата ---
  const fetchMessages = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/support-tickets/${ticketId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) throw new Error('Не удалось загрузить чат');
      const data = await response.json();
      setTicket(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [ticketId, token]);

  useEffect(() => {
    fetchMessages();
  }, [fetchMessages]);

  // --- 2. Отправка ответа (Админом) ---
  const handleReply = async (e) => {
    e.preventDefault();
    if (!message.trim()) return;
    
    try {
      const response = await fetch(`/api/support-tickets/${ticketId}/reply`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: message })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || 'Ошибка отправки');
      
      setTicket(prev => ({ ...prev, messages: [...prev.messages, data] }));
      setMessage(''); 
    } catch (e) {
      alert(e.message);
    }
  };
  
  // --- 3. Смена статуса (Закрыть/Открыть) ---
  const toggleStatus = async () => {
    const newStatus = ticket.status === 'OPEN' ? 'CLOSED' : 'OPEN';
    try {
      await fetch(`/api/admin/support-tickets/${ticketId}`, {
        method: 'PATCH',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      });
      setTicket(prev => ({ ...prev, status: newStatus }));
      onStatusChange(ticketId, newStatus); 
    } catch (e) { alert(e.message); }
  };

  if (loading) return <div className="chat-window loading">Загрузка чата...</div>;
  if (error) return <div className="chat-window error">{error}</div>;
  if (!ticket) return null;

  const adminId = user ? user.id : null; 

  return (
    <div className="chat-window">
      <header className="chat-header">
        <div>
          <h3>{ticket.subject}</h3>
          <span className="chat-user">от: {ticket.user_email}</span>
        </div>
        <button 
          onClick={toggleStatus} 
          className={`btn-table-toggle ${ticket.status === 'CLOSED' ? 'closed' : 'open'}`}
        >
          {ticket.status === 'OPEN' ? 'Закрыть' : 'Открыть'}
        </button>
      </header>
      
      <div className="chat-messages">
        {ticket.messages.map(msg => (
          <div 
            key={msg.id} 
            className={`chat-bubble ${msg.sender_id === adminId ? 'me' : 'them'}`}
          >
            <div className="bubble-sender">{msg.sender_email}</div>
            <div className="bubble-message">{msg.message}</div>
            <div className="bubble-time">{new Date(msg.created_at).toLocaleTimeString('ru-RU')}</div>
          </div>
        ))}
      </div>
      
      <form className="chat-input-form" onSubmit={handleReply}>
        <input 
          type="text" 
          placeholder="Написать ответ..." 
          value={message}
          onChange={(e) => setMessage(e.target.value)}
        />
        <button type="submit" className="btn-send"><LuSend /></button>
      </form>
    </div>
  );
};


// ---------------------------------
// ❗️ ОСНОВНАЯ СТРАНИЦА АДМИНКИ ❗️
// ---------------------------------
function AdminSupportPage() {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { token } = useAuth();
  const { ticketId } = useParams(); 
  const navigate = useNavigate();

  // --- 1. Загрузка списка тикетов (для левой панели) ---
  // ❗️ ИСПРАВЛЕНИЕ: fetchTickets теперь ВНУТРИ useEffect
  useEffect(() => {
    const fetchTickets = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch('/api/admin/support-tickets', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) throw new Error('Не удалось загрузить тикеты');
        const data = await response.json();
        setTickets(data);
      } catch (e) { 
        setError(e.message); 
      } finally { 
        setLoading(false); 
      }
    };
    
    if (token) {
        fetchTickets();
    }
  }, [token]);

  // --- 2. Обновление статуса в списке ---
  const handleStatusChange = (id, newStatus) => {
    setTickets(prev => prev.map(t => t.id === id ? { ...t, status: newStatus } : t));
  };
  
  const formatTicketDate = (dateString) => new Date(dateString).toLocaleDateString('ru-RU');

  return (
    <main className="admin-page-content">
      <div className="support-chat-layout">
        
        {/* --- 1. Левая панель (Список тикетов) --- */}
        <div className="chat-list-sidebar">
          <div className="chat-list-header">
            <h2>Тикеты поддержки</h2>
          </div>
          {loading && <div className="loading-mini">Загрузка...</div>}
          {error && <div className="message-error">{error}</div>}
          
          <div className="chat-list-items">
            {tickets.map(ticket => (
              <div 
                key={ticket.id} 
                className={`chat-list-item ${ticket.id === parseInt(ticketId) ? 'active' : ''} ${ticket.status === 'CLOSED' ? 'closed' : ''}`}
                onClick={() => navigate(`/admin/support/${ticket.id}`)} 
              >
                <div className="item-header">
                  <span className="item-email">{ticket.user_email}</span>
                  <span className="item-date">{formatTicketDate(ticket.created_at)}</span>
                </div>
                <div className="item-subject">{ticket.subject}</div>
                <span className={`status-badge-small status-${ticket.status}`}>{ticket.status}</span>
              </div>
            ))}
          </div>
        </div>
        
        {/* --- 2. Правая панель (Чат) --- */}
        <div className="chat-window-wrapper">
          {ticketId ? (
            <AdminChatInterface 
              ticketId={ticketId} 
              token={token}
              onStatusChange={handleStatusChange} 
            />
          ) : (
            <div className="chat-window empty">
              Выберите тикет из списка слева, чтобы начать чат.
            </div>
          )}
        </div>
        
      </div>
    </main>
  );
}

export default AdminSupportPage;
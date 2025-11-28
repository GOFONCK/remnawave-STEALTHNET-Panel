import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../../AuthContext';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from 'react-router-dom';
import { LuSend } from 'react-icons/lu';
import './SupportChat.css'; // ❗️ Убедитесь, что этот импорт есть

// ---------------------------------
// ❗️ КОМПОНЕНТ "ИНТЕРФЕЙС ЧАТА" (Клиентский) ❗️
// ---------------------------------
const ClientChatInterface = ({ ticketId, token, onReply }) => {
  const [ticket, setTicket] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [message, setMessage] = useState('');
  const { user } = useAuth(); // Мы используем 'user', чтобы знать ID клиента

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

  // --- 2. Отправка ответа (Клиентом) ---
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
      onReply(); // Сообщаем списку, что тикет обновлен
    } catch (e) {
      alert(e.message);
    }
  };
  
  if (loading) return <div className="chat-window loading">Загрузка чата...</div>;
  if (error) return <div className="chat-window error">{error}</div>;
  if (!ticket) return null;

  const clientId = user ? user.id : null; // ID залогиненного клиента

  return (
    <div className="chat-window">
      <header className="chat-header">
        <div>
          <h3>{ticket.subject}</h3>
          <span className={`status-badge-small status-${ticket.status}`}>{ticket.status}</span>
        </div>
      </header>
      
      <div className="chat-messages">
        {ticket.messages.map(msg => (
          <div 
            key={msg.id} 
            className={`chat-bubble ${msg.sender_id === clientId ? 'me' : 'them'}`}
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
          disabled={ticket.status === 'CLOSED'} 
        />
        <button type="submit" className="btn-send" disabled={ticket.status === 'CLOSED'}>
          <LuSend />
        </button>
      </form>
    </div>
  );
};

// ---------------------------------
// ❗️ КОМПОНЕНТ "СОЗДАТЬ ТИКЕТ" ❗️
// ---------------------------------
const CreateTicketForm = ({ token, onTicketCreated }) => {
  const { t } = useTranslation(); 
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/client/support-tickets', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ subject, message })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || t('support.error_generic'));
      
      onTicketCreated(data.ticket_id); 
      
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };
  
  return (
    <section>
      <h2>{t('support.create_title', 'Создать новый тикет')}</h2>
      {/* ❗️❗️❗️ ИСПРАВЛЕНИЕ: CSS-класс "support-form" ❗️❗️❗️ */}
      <form className="support-form" onSubmit={handleSubmit}>
        <div className="form-group">
          <label>{t('support.subject', 'Тема')}</label>
          <input type="text" value={subject} onChange={e => setSubject(e.target.value)} required />
        </div>
        <div className="form-group">
          <label>{t('support.message_label')}</label>
          <textarea 
            rows="4" 
            value={message} 
            onChange={e => setMessage(e.target.value)} 
            placeholder={t('support.placeholder')}
            required
          ></textarea>
        </div>
        {error && <div className="message-error">{error}</div>}
        <button type="submit" className="btn" style={{maxWidth: '200px'}} disabled={loading}>
          {loading ? t('support.sending') : t('support.create_button', 'Создать тикет')}
        </button>
      </form>
    </section>
  )
}

// ---------------------------------
// ❗️ ОСНОВНАЯ СТРАНИЦА КЛИЕНТА ❗️
// ---------------------------------
export default function ClientSupportPage() {
  const { t } = useTranslation(); 
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const { token } = useAuth();
  const { ticketId } = useParams(); 
  const navigate = useNavigate();

  // --- 1. Загрузка списка тикетов (только своих) ---
  const fetchTickets = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // ❗️❗️❗️ ИСПРАВЛЕНИЕ: Используем /api/client/... ❗️❗️❗️
      const response = await fetch('/api/client/support-tickets', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (!response.ok) throw new Error('Не удалось загрузить тикеты'); // 👈 Вот ваша ошибка
      const data = await response.json();
      setTickets(data);
    } catch (e) { 
      setError(e.message); 
    } finally { 
      setLoading(false); 
    }
  }, [token]);
  
  useEffect(() => {
    fetchTickets();
  }, [fetchTickets]);

  // --- 2. Обработчик: Тикет создан ИЛИ получен ответ ---
  const handleTicketUpdate = (newTicketId) => {
    fetchTickets(); // Обновляем список
    if (newTicketId) {
        navigate(`/dashboard/support/${newTicketId}`);
    }
  };
  
  const formatTicketDate = (dateString) => new Date(dateString).toLocaleDateString('ru-RU');

  return (
    <main className="client-page-content">
      <div className="support-chat-layout">
        
        {/* --- 1. Левая панель (Список тикетов) --- */}
        <div className="chat-list-sidebar">
          <div className="chat-list-header">
            <h2>{t('support.my_tickets', 'Мои тикеты')}</h2>
          </div>
          {loading && <div className="loading-mini">Загрузка...</div>}
          {error && <div className="message-error">{error}</div>}
          
          <div className="chat-list-items">
            {tickets.map(ticket => (
              <div 
                key={ticket.id} 
                className={`chat-list-item ${ticket.id === parseInt(ticketId) ? 'active' : ''} ${ticket.status === 'CLOSED' ? 'closed' : ''}`}
                onClick={() => navigate(`/dashboard/support/${ticket.id}`)}
              >
                <div className="item-header">
                  <span className="item-email">{t('support.ticket_num', 'Тикет #')}{ticket.id}</span>
                  <span className="item-date">{formatTicketDate(ticket.created_at)}</span>
                </div>
                <div className="item-subject">{ticket.subject}</div>
                <span className={`status-badge-small status-${ticket.status}`}>{ticket.status}</span>
              </div>
            ))}
          </div>
          {/* Кнопка "Создать новый" (показывает форму справа) */}
          <button 
            className="btn" 
            style={{margin: '15px', width: 'auto'}}
            onClick={() => navigate('/dashboard/support')}
          >
            {t('support.create_new', '+ Создать тикет')}
          </button>
        </div>
        
        {/* --- 2. Правая панель (Чат ИЛИ Форма) --- */}
        <div className="chat-window-wrapper">
          {ticketId ? (
            <ClientChatInterface 
              ticketId={ticketId} 
              token={token}
              onReply={handleTicketUpdate} 
            />
          ) : (
            <div className="chat-window empty">
              {/* Если тикет не выбран, показываем форму создания */}
              <CreateTicketForm 
                token={token} 
                onTicketCreated={handleTicketUpdate} 
              />
            </div>
          )}
        </div>
        
      </div>
    </main>
  );
}
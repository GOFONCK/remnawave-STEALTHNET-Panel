import React, { useState, useEffect } from 'react';
import { useAuth } from '../AuthContext';
import { useTranslation } from 'react-i18next';

function AdminBroadcastPage() {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [recipientType, setRecipientType] = useState('all');
  const [customEmails, setCustomEmails] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [usersEmails, setUsersEmails] = useState([]);
  const [loadingEmails, setLoadingEmails] = useState(false);

  // Загрузка списка email пользователей
  useEffect(() => {
    const fetchEmails = async () => {
      setLoadingEmails(true);
      try {
        const response = await fetch('/api/admin/users/emails', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
          const data = await response.json();
          setUsersEmails(data);
        }
      } catch (e) {
        console.error('Ошибка загрузки email:', e);
      } finally {
        setLoadingEmails(false);
      }
    };
    
    if (token) {
      fetchEmails();
    }
  }, [token]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      let recipients = [];
      if (recipientType === 'custom') {
        const emails = customEmails.split('\n')
          .map(email => email.trim())
          .filter(email => email && email.includes('@'));
        recipients = emails;
      }

      const response = await fetch('/api/admin/broadcast', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          subject: subject,
          message: message,
          recipient_type: recipientType,
          custom_emails: recipientType === 'custom' ? recipients : []
        })
      });

      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.message || 'Ошибка отправки рассылки');
      }

      setSuccess({
        total: data.total_recipients,
        sent: data.sent,
        failed: data.failed
      });
      
      // Очищаем форму
      setSubject('');
      setMessage('');
      setCustomEmails('');
      
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const recipientTypeLabels = {
    all: 'Всем пользователям',
    active: 'Только активным пользователям',
    inactive: 'Только неактивным пользователям',
    custom: 'Указанным email адресам'
  };

  return (
    <main className="admin-page-content">
      <section>
        <h2 className="admin-page-title">{t('broadcast.title')}</h2>
        <p className="admin-description-text">
          {t('broadcast.description')}
        </p>

        {error && <div className="message-error">{error}</div>}
        {success && (
          <div className="message-success">
            <strong>{t('broadcast.success_title')}</strong>
            <p>{t('broadcast.success_total')}: {success.total}</p>
            <p>{t('broadcast.success_sent')}: {success.sent}</p>
            {success.failed > 0 && <p>{t('broadcast.success_failed')}: {success.failed}</p>}
          </div>
        )}

        <form onSubmit={handleSubmit} className="broadcast-form">
          <div className="form-group">
            <label htmlFor="recipient_type">{t('broadcast.recipients')}</label>
            <select
              id="recipient_type"
              value={recipientType}
              onChange={(e) => setRecipientType(e.target.value)}
              style={{ width: '100%' }}
            >
              <option value="all">{t('broadcast.recipient_all')} ({usersEmails.length})</option>
              <option value="active">{t('broadcast.recipient_active')}</option>
              <option value="inactive">{t('broadcast.recipient_inactive')}</option>
              <option value="custom">{t('broadcast.recipient_custom')}</option>
            </select>
            <small>{t('broadcast.recipient_hint')}</small>
          </div>

          {recipientType === 'custom' && (
            <div className="form-group">
              <label htmlFor="custom_emails">{t('broadcast.custom_emails')}</label>
              <textarea
                id="custom_emails"
                value={customEmails}
                onChange={(e) => setCustomEmails(e.target.value)}
                placeholder={t('broadcast.custom_emails_placeholder')}
                rows={6}
                style={{ width: '100%', fontFamily: 'monospace' }}
              />
              <small>{t('broadcast.custom_emails_hint')}</small>
            </div>
          )}

          <div className="form-group">
            <label htmlFor="subject">{t('broadcast.subject')} *</label>
            <input
              type="text"
              id="subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder={t('broadcast.subject_placeholder')}
              required
              style={{ width: '100%' }}
            />
          </div>

          <div className="form-group">
            <label htmlFor="message">{t('broadcast.message')} *</label>
            <textarea
              id="message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder={t('broadcast.message_placeholder')}
              required
              rows={12}
              style={{ width: '100%', minHeight: '200px' }}
            />
            <small>{t('broadcast.message_hint')}</small>
          </div>

          <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
            <button type="submit" className="btn" disabled={loading}>
              {loading ? t('broadcast.sending') : t('broadcast.send_button')}
            </button>
            {loading && (
              <span style={{ color: 'var(--text-secondary)' }}>
                {t('broadcast.sending_hint')}
              </span>
            )}
          </div>
        </form>

        {usersEmails.length > 0 && (
          <div className="broadcast-users-list" style={{ marginTop: '40px', padding: '20px', background: 'var(--surface-muted)', borderRadius: '12px' }}>
            <h3 style={{ marginTop: 0 }}>{t('broadcast.users_list')} ({usersEmails.length})</h3>
            <div style={{ maxHeight: '300px', overflowY: 'auto', fontFamily: 'monospace', fontSize: '13px' }}>
              {usersEmails.map((user, idx) => (
                <div key={idx} style={{ padding: '4px 0', borderBottom: '1px solid var(--glass-border)' }}>
                  {user.email} {user.is_verified ? t('broadcast.user_verified') : t('broadcast.user_unverified')}
                </div>
              ))}
            </div>
          </div>
        )}
      </section>
    </main>
  );
}

export default AdminBroadcastPage;


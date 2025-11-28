import React, { useMemo, useState } from 'react';
import { useAuth } from '../../AuthContext';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { 
  LuCircleCheck, LuCircleX, LuClock, LuUser, LuDatabase, 
  LuActivity, LuShieldCheck, LuDownload, LuGift, LuTicket,
  LuHourglass, LuSparkles, LuArrowRight, LuLifeBuoy, LuUsers,
  LuPlus
} from 'react-icons/lu';
import { FaWindows, FaApple } from 'react-icons/fa';

// --- Виджет: Триал ---
const TrialCard = ({ onActivateTrial, loading, error }) => {
  const { t } = useTranslation();
  return (
    <div className="glass-card trial-card gradient-card">
      <div className="trial-icon-wrapper"><LuGift /></div>
      <div className="trial-content">
        <p className="eyebrow-text">{t('trial.no_subscription')}</p>
        <h3>{t('trial.hero_title', 'Получите 3 дня премиум')}</h3>
        <p>{t('trial.cta_desc', 'Дадим полный доступ без ограничений — протестируйте сеть перед оплатой.')}</p>
      </div>
      <div className="trial-actions">
        <button className="btn btn-trial" onClick={onActivateTrial} disabled={loading}>
          {loading ? t('trial.activating') : t('trial.cta')}
        </button>
      </div>
      {error && <div className="message-error" style={{marginTop: '15px'}}>{error}</div>}
    </div>
  );
};

// --- Виджет: Промокод ---
const PromoCodeWidget = ({ onUpdateUser }) => {
  const { token } = useAuth();
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState(null);

  const handleActivate = async (e) => {
    e.preventDefault();
    if(!code.trim()) return;
    
    setLoading(true); setStatus(null);
    try {
      const response = await fetch('/api/client/activate-promocode', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ code })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message);
      
      setStatus({ type: 'success', msg: data.message });
      setCode('');
      
      setTimeout(() => window.location.reload(), 1500); 
      
    } catch (err) {
      setStatus({ type: 'error', msg: err.message });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-card info-card softer-card promo-card">
      <h3 className="client-widget-title"><LuTicket style={{marginRight: 8}}/> Активация промокода</h3>
      <form onSubmit={handleActivate} className="promo-form">
        <div className="input-with-button">
          <input 
            type="text" 
            placeholder="Введите код..." 
            value={code} 
            onChange={e => setCode(e.target.value)} 
            disabled={loading} 
          />
          <button className="btn-copy" type="submit" disabled={loading}>
            {loading ? '...' : 'OK'}
          </button>
        </div>
        {status && (
          <div className={`message-${status.type}`} style={{marginTop: 10, fontSize: 14}}>
            {status.msg}
          </div>
        )}
      </form>
    </div>
  );
};

// --- Виджет Информации ---
const SubscriptionInfoCard = ({ user, isTrulyActive, formattedDate, squadName }) => {
  const { t } = useTranslation();

  const daysLeft = useMemo(() => {
    if (!user.expireAt) return 0;
    const now = new Date();
    const expire = new Date(user.expireAt);
    const diffTime = expire - now;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)); 
    return diffDays > 0 ? diffDays : 0;
  }, [user.expireAt]);

  return (
    <div className="glass-card info-card accent-card">
      <h3 className="client-widget-title">{t('dashboard.details_title')}</h3>
      <div className="info-list modern">
        <div className="info-item modern">
          <span className="info-label"><LuUser /> Email</span>
          <span className="info-value">{user.email}</span>
        </div>
        <div className="info-item modern">
          <span className="info-label"><LuActivity /> {t('dashboard.status')}</span>
          {isTrulyActive ? (
            <span className="status-chip success"><LuCircleCheck /> Активна</span>
          ) : (
            <span className="status-chip danger"><LuCircleX /> Не активна</span>
          )}
        </div>
        {isTrulyActive && (
          <>
            <div className="info-item modern">
              <span className="info-label"><LuClock /> {t('dashboard.expires_at')}</span>
              <span className="info-value">{formattedDate}</span>
            </div>
            <div className="info-item modern">
              <span className="info-label"><LuHourglass /> {t('dashboard.days_left', 'Осталось дней')}</span>
              <span className={`info-value ${daysLeft <= 3 ? 'text-warning' : ''}`}>
                {daysLeft}
              </span>
            </div>
          </>
        )}
        <div className="info-item modern">
          <span className="info-label"><LuShieldCheck /> Тариф</span>
          <span className="info-value">{squadName}</span>
        </div>
      </div>
    </div>
  );
};

const TrafficUsageCard = ({ user }) => {
  const { t } = useTranslation();
  const formatBytes = (bytes, decimals = 2) => { if (!bytes) return '0 B'; const k = 1024; const i = Math.floor(Math.log(bytes) / Math.log(k)); return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + ['B', 'KB', 'MB', 'GB', 'TB'][i]; };
  const used = user.usedTrafficBytes || 0;
  const limit = user.trafficLimitBytes || 0; 
  const isUnlimited = limit === 0;
  const percentage = (!isUnlimited && used > 0) ? Math.min((used / limit) * 100, 100) : 0;

  return (
    <div className="glass-card info-card softer-card">
      <h3 className="client-widget-title">{t('dashboard.traffic_title')}</h3>
      {isUnlimited ? (
        <div className="traffic-stats unlimited"><span>Безлимит</span><LuActivity /></div>
      ) : (
        <>
          <div className="progress-bar-container"><div className="progress-bar-fill" style={{ width: `${percentage}%` }}></div></div>
          <div className="traffic-stats"><span>{formatBytes(used)}</span><span>{formatBytes(limit)}</span></div>
        </>
      )}
      <div className="info-list" style={{marginTop: '20px'}}>
         <div className="info-item">
            <span className="info-label"><LuDatabase /> Всего</span>
            <span className="info-value">{formatBytes(user.lifetimeUsedTrafficBytes || 0)}</span>
         </div>
      </div>
    </div>
  );
};

const QuickDownloadCard = ({ connectUrl }) => {
  const { t } = useTranslation();
  
  const profileUrl = connectUrl ? `stealthnet://install-config?url=${encodeURIComponent(connectUrl)}` : null;
  
  return (
    <section className="glass-card quick-download-section">
      <h3 className="client-widget-title">{t('dashboard.quick_download_title')}</h3>
      <div className="quick-download-buttons">
        <a 
          href="https://stealthnet.app/downloads/StealthNet-Setup.exe" 
          className="btn btn-download btn-windows"
          target="_blank"
          rel="noopener noreferrer"
        >
          <FaWindows /> {t('dashboard.download_windows')}
        </a>
        <a 
          href="https://stealthnet.app/downloads/StealthNet-1.0.1-arm64.dmg" 
          className="btn btn-download btn-macos"
          target="_blank"
          rel="noopener noreferrer"
        >
          <FaApple /> {t('dashboard.download_macos')}
        </a>
        {profileUrl ? (
          <a 
            href={profileUrl}
            className="btn btn-download btn-profile"
          >
            <LuPlus /> {t('dashboard.add_profile')}
          </a>
        ) : (
          <button 
            className="btn btn-download btn-profile"
            disabled
          >
            <LuPlus /> {t('dashboard.add_profile')}
          </button>
        )}
      </div>
    </section>
  );
};

const HeroCard = ({
  isTrulyActive,
  formattedDate,
  onUpgrade,
  onActivateTrial,
  trialLoading,
  daysLeft,
  connectUrl
}) => {
  const { t } = useTranslation();
  const noSubscriptionLabel = t('dashboard.no_subscription', 'У вас нет подписки');

  return (
    <section className="hero-card glass-panel gradient-card">
      <div className="hero-container">
        <div className="hero-main">
          <p className="eyebrow-text"><LuSparkles /> {t('dashboard.hero_label', 'Ваш трафик под защитой')}</p>
          <h2>{isTrulyActive ? t('dashboard.hero_active', 'Подписка активна') : t('dashboard.hero_inactive', 'Нет активной подписки')}</h2>
          <p>{isTrulyActive ? t('dashboard.hero_active_desc', 'Мы удерживаем соединение стабильным и быстрым по всему миру.') : t('dashboard.hero_inactive_desc', 'Подключите тариф или активируйте триал, чтобы получить самый быстрый VPN.')}</p>
          <div className="hero-status-row">
            <span className={`status-dot ${isTrulyActive ? 'online' : 'offline'}`}></span>
            <span>{isTrulyActive ? `${t('dashboard.expires_at')}: ${formattedDate}` : noSubscriptionLabel}</span>
          </div>
          <div className="quick-metrics">
            <div>
              <p>{t('dashboard.days_left', 'Осталось дней')}</p>
              <strong>{isTrulyActive ? daysLeft : '—'}</strong>
            </div>
          </div>
          <div className="hero-quick-actions">
            <button className="chip-btn" onClick={onUpgrade}>
              <LuShieldCheck /> {t('dashboard.hero_plans', 'Тарифы')}
            </button>
            <button className="chip-btn secondary">
              <LuLifeBuoy /> {t('dashboard.hero_support', 'Поддержка 24/7')}
            </button>
            <button className="chip-btn secondary">
              <LuUsers /> {t('dashboard.hero_ref', 'Реферальная программа')}
            </button>
          </div>
        </div>
        <div className="hero-actions">
          {isTrulyActive ? (
            <>
              <button className="btn btn-primary hero-cta" type="button" onClick={onUpgrade}>
                {t('dashboard.hero_cta', 'Продлить подписку')} <LuArrowRight />
              </button>
              {connectUrl && (
                <div className="hero-connect-block">
                  <div className="hero-connect-info">
                    <span>{t('dashboard.connect_desc', 'Нажмите подключиться и следуйте инструкциям')}</span>
                  </div>
                  <button className="btn btn-connect hero-connect-btn" type="button" onClick={() => { if (connectUrl) window.location.href = connectUrl; }}>
                    <LuDownload /> {t('dashboard.connect_button', 'Подключиться')}
                  </button>
                </div>
              )}
            </>
          ) : (
            <button className="btn btn-primary hero-cta" type="button" onClick={onUpgrade}>
              {t('dashboard.hero_plans', 'Выбрать тариф')} <LuArrowRight />
            </button>
          )}
        </div>
      </div>
    </section>
  );
};

export default function ClientStatusPage() {
  const { i18n } = useTranslation(); 
  const { user, setUser, token } = useAuth(); 
  const navigate = useNavigate();
  const [trialLoading, setTrialLoading] = useState(false);
  const [trialError, setTrialError] = useState(null);

  if (!user) return <div className="loading-mini">Загрузка...</div>;

  const isSubActive = user.activeInternalSquads?.length > 0;
  const isExpired = new Date(user.expireAt) < new Date();
  const isTrulyActive = isSubActive && !isExpired;
  const formattedDate = new Date(user.expireAt).toLocaleDateString(i18n.language);
  const squadName = isSubActive ? user.activeInternalSquads[0].name : "Нет";
  const daysLeft = (() => {
    if (!user.expireAt) return 0;
    const now = new Date();
    const expire = new Date(user.expireAt);
    const diffTime = expire - now;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24)); 
    return diffDays > 0 ? diffDays : 0;
  })();

  const handleActivateTrial = async () => {
    if (trialLoading) return;
    setTrialLoading(true);
    setTrialError(null);
    try {
      const response = await fetch('/api/client/activate-trial', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || 'Ошибка активации');

      const meResponse = await fetch('/api/client/me', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (meResponse.ok) {
        const meData = await meResponse.json();
        setUser(meData.response || meData);
      } else {
        setUser((prev) => ({ ...prev, ...(data?.response || {}) }));
      }
    } catch (err) {
      setTrialError(err.message);
    } finally {
      setTrialLoading(false);
    }
  };

  return (
    <main className="client-page-content modern">
      <HeroCard 
        isTrulyActive={isTrulyActive} 
        formattedDate={formattedDate}
        onUpgrade={() => navigate('/dashboard/tariffs')}
        onActivateTrial={handleActivateTrial}
        trialLoading={trialLoading}
        daysLeft={daysLeft}
        connectUrl={user.subscriptionUrl}
      />

      <QuickDownloadCard connectUrl={user.subscriptionUrl} />

      {!isTrulyActive ? (
        <div className="client-grid no-subscription">
          <div className="grid-full">
            <TrialCard
              onActivateTrial={handleActivateTrial}
              loading={trialLoading}
              error={trialError}
            />
          </div>
        </div>
      ) : (
        <div className="client-grid">
          <SubscriptionInfoCard user={user} isTrulyActive={isTrulyActive} formattedDate={formattedDate} squadName={squadName} />
          <TrafficUsageCard user={user} />
          <PromoCodeWidget onUpdateUser={(u) => setUser(u)} />
        </div>
      )}
    </main>
  );
}
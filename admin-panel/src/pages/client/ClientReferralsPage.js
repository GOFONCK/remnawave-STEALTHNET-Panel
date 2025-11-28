import React, { useState } from 'react'; // ❗️ Добавлен useState
import { useAuth } from '../../AuthContext';
import { useTranslation } from 'react-i18next';
import { LuCopy, LuCheck } from 'react-icons/lu'; // ❗️ Иконки

export default function ClientReferralsPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  
  // ❗️ Новое состояние для кнопки "Копировать"
  const [isCopied, setIsCopied] = useState(false);

  if (!user) return <div className="loading-mini">Загрузка...</div>;

  const referralLink = `https://panel.stealthnet.app/register?ref=${user.referral_code}`;

  // ❗️ Новая функция "Копировать"
  const handleCopy = () => {
    navigator.clipboard.writeText(referralLink);
    setIsCopied(true);
    // Сбрасываем иконку "Скопировано" через 2 секунды
    setTimeout(() => {
      setIsCopied(false);
    }, 2000);
  };

  return (
    <main className="client-page-content">
      <section className="referral-section">
        <h2>{t('dashboard.referral_title')}</h2>
        <p>{t('dashboard.referral_desc')}</p>
        
        {user.referral_code ? (
          // ❗️❗️❗️ НОВЫЙ ДИЗАЙН ❗️❗️❗️
          <div className="input-with-button">
            <input 
              type="text" 
              value={referralLink} 
              readOnly 
            />
            <button className="btn-copy" onClick={handleCopy} title="Копировать">
              {isCopied ? <LuCheck /> : <LuCopy />}
            </button>
          </div>
        ) : (
          <div className="empty-state">Ваш реферальный код генерируется.</div>
        )}
      </section>
      
      {/* TODO: Добавить секцию со статистикой (сколько пригласил) */}
    </main>
  );
}
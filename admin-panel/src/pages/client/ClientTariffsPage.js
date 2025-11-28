import React, { useState, useEffect, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { useAuth } from '../../AuthContext';
import { useTranslation } from 'react-i18next';

const currencyConfig = {
  uah: { field: 'price_uah', code: 'UAH' },
  rub: { field: 'price_rub', code: 'RUB' },
  usd: { field: 'price_usd', code: 'USD' }
};

const PLATEGA_METHOD_LABELS = {
  2: 'СБП QR (НСПК / QR)',
  10: 'Карты (RUB) — МИР/Visa/Mastercard',
  11: 'Карточный эквайринг',
  12: 'Международный эквайринг',
  13: 'Криптовалюта'
};

const featurePresets = {
  basic: ['Безлимитный трафик', 'До 5 устройств', 'Базовый анти-DPI'],
  pro: ['Приоритетная скорость', 'До 10 устройств', 'Ротация IP-адресов'],
  elite: ['VIP-поддержка 24/7', 'Статический IP по запросу', 'Автообновление ключей']
};

// Бейджи для tier'ов (может использоваться в будущем)
// Пример: { basic: 'Популярный', pro: 'ТОП-продажа', elite: 'Максимальная выгода' }
// eslint-disable-next-line no-unused-vars
const tierBadges = {};

const getTier = (tariff) => {
  // Если tier указан в тарифе, используем его
  if (tariff.tier && ['basic', 'pro', 'elite'].includes(tariff.tier)) {
    return tariff.tier;
  }
  // Иначе определяем автоматически по длительности (обратная совместимость)
  const duration = tariff.duration_days;
  if (duration >= 180) return 'elite';
  if (duration >= 90) return 'pro';
  return 'basic';
};

// Функция для правильного склонения слова "день/дня/дней" с учетом языка
const getDaysText = (count, language) => {
  if (language === 'ru') {
    const lastDigit = count % 10;
    const lastTwoDigits = count % 100;
    
    if (lastTwoDigits >= 11 && lastTwoDigits <= 19) {
      return 'дней';
    }
    if (lastDigit === 1) {
      return 'день';
    }
    if (lastDigit >= 2 && lastDigit <= 4) {
      return 'дня';
    }
    return 'дней';
  } else if (language === 'ua') {
    const lastDigit = count % 10;
    const lastTwoDigits = count % 100;
    
    if (lastTwoDigits >= 11 && lastTwoDigits <= 19) {
      return 'днів';
    }
    if (lastDigit === 1) {
      return 'день';
    }
    if (lastDigit >= 2 && lastDigit <= 4) {
      return 'дні';
    }
    return 'днів';
  } else if (language === 'cn') {
    return '天';
  } else {
    // English
    return count === 1 ? 'day' : 'days';
  }
};

// Функция для перевода названия тарифа (заменяет "Дней"/"дней"/"дня"/"день"/"Days"/"days"/"day" на переведенную версию)
const translateTariffName = (name, durationDays, language) => {
  if (!name) return name;
  
  // Паттерны для поиска слова "дней" в разных формах (русский/украинский)
  const ruUaPatterns = [
    /\d+\s+Дней/gi,
    /\d+\s+дней/gi,
    /\d+\s+дня/gi,
    /\d+\s+день/gi,
    /\d+\s+День/gi,
    /\d+\s+Дня/gi,
    /\d+\s+Днів/gi,
    /\d+\s+днів/gi,
    /\d+\s+дні/gi
  ];
  
  // Паттерны для английского
  const enPatterns = [
    /\d+\s+Days/gi,
    /\d+\s+days/gi,
    /\d+\s+Day/gi,
    /\d+\s+day/gi
  ];
  
  // Паттерны для китайского
  const cnPatterns = [
    /\d+\s+天/gi
  ];
  
  // Объединяем все паттерны
  const allPatterns = [...ruUaPatterns, ...enPatterns, ...cnPatterns];
  
  // Если название содержит число и слово дней/дня/день/Days/days/day/天, заменяем его
  for (const pattern of allPatterns) {
    if (pattern.test(name)) {
      const daysText = getDaysText(durationDays, language);
      // Заменяем найденное совпадение на число + переведенное слово
      // Для английского и китайского используем правильный регистр
      if (language === 'en') {
        return name.replace(pattern, `${durationDays} ${daysText.charAt(0).toUpperCase() + daysText.slice(1)}`);
      } else if (language === 'cn') {
        return name.replace(pattern, `${durationDays} ${daysText}`);
      } else {
        // Для русского и украинского - с заглавной буквы
        return name.replace(pattern, `${durationDays} ${daysText.charAt(0).toUpperCase() + daysText.slice(1)}`);
      }
    }
  }
  
  // Если паттерн не найден, возвращаем оригинальное название
  return name;
};

const TariffSection = () => {
  const { t, i18n } = useTranslation();
  const { currency, token } = useAuth();
  const [tariffs, setTariffs] = useState([]);
  const [features, setFeatures] = useState(featurePresets); // Используем дефолтные, потом заменим из API
  const [loading, setLoading] = useState(true);
  const [loadingTariffId, setLoadingTariffId] = useState(null);
  const [error, setError] = useState(null);
  const [promoCode, setPromoCode] = useState('');
  const [appliedPromo, setAppliedPromo] = useState(null); // { code, type, value, discount }
  const [promoError, setPromoError] = useState(null);
  const [selectedTariffId, setSelectedTariffId] = useState(null);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [plategaMethods, setPlategaMethods] = useState([]);

  useEffect(() => {
    const fetchTariffs = async () => {
      setLoading(true);
      try {
        const [tariffsResponse, featuresResponse] = await Promise.all([
          fetch('/api/public/tariffs'),
          fetch('/api/public/tariff-features')
        ]);
        
        if (tariffsResponse.ok) {
          const tariffsData = await tariffsResponse.json();
          console.log('Loaded tariffs:', tariffsData); // Для отладки
          setTariffs(tariffsData);
        }
        
        if (featuresResponse.ok) {
          const featuresData = await featuresResponse.json();
          console.log('Loaded features from API:', featuresData);
          // Убеждаемся, что все ключи присутствуют
          const mergedFeatures = {
            basic: featuresData.basic || featurePresets.basic || [],
            pro: featuresData.pro || featurePresets.pro || [],
            elite: featuresData.elite || featurePresets.elite || []
          };
          setFeatures(mergedFeatures);
        } else {
          console.warn('Failed to load features, using defaults');
          setFeatures(featurePresets);
        }
      } catch (e) {
        console.error('Не удалось загрузить данные', e);
      } finally {
        setLoading(false);
      }
    };
    fetchTariffs();
  }, []);

  useEffect(() => {
    const fetchPlategaMethods = async () => {
      try {
        const resp = await fetch('/api/public/platega-methods');
        if (resp.ok) {
          const data = await resp.json();
          if (Array.isArray(data.methods)) setPlategaMethods(data.methods);
        }
      } catch (e) {
        console.warn('Failed to load platega methods', e);
      }
    };
    fetchPlategaMethods();
  }, []);

  const intlFormatter = useMemo(() => {
    const config = currencyConfig[currency] || currencyConfig.uah;
    return new Intl.NumberFormat('ru-RU', {
      style: 'currency',
      currency: config.code,
      maximumFractionDigits: 0
    });
  }, [currency]);

  const formatPrice = (tariff) => {
    const config = currencyConfig[currency] || currencyConfig.uah;
    const value = Number(tariff[config.field]) || 0;
    const formatted = intlFormatter.format(value);
    const perDay = tariff.duration_days ? value / tariff.duration_days : value;
    const perDayFormatted = new Intl.NumberFormat('ru-RU', {
      style: 'currency',
      currency: config.code,
      maximumFractionDigits: 2
    }).format(perDay);
    return { formatted, perDayFormatted, value };
  };

  const handleApplyPromo = async () => {
    if (!promoCode.trim()) {
      setPromoError('Введите промокод');
      return;
    }
    
    setPromoError(null);
    try {
      const response = await fetch('/api/client/check-promocode', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ code: promoCode.trim().toUpperCase() })
      });
      const data = await response.json();
      
      if (response.ok) {
        if (data.promo_type === 'PERCENT') {
          setAppliedPromo({ 
            code: data.code, 
            type: 'PERCENT', 
            value: data.value,
            discount: data.value 
          });
          setPromoError(null);
        } else if (data.promo_type === 'DAYS') {
          // Для бесплатных дней нужно активировать отдельно
          setPromoError('Промокод на бесплатные дни активируется на странице подписки');
          setAppliedPromo(null);
        }
      } else {
        setPromoError(data.message || 'Неверный промокод');
        setAppliedPromo(null);
      }
    } catch (e) {
      setPromoError('Ошибка проверки промокода');
      setAppliedPromo(null);
    }
  };

  const handleSelectTariff = (tariffId) => {
    setSelectedTariffId(tariffId);
    setShowPaymentModal(true);
  };

  const handleCreatePayment = async (paymentProvider, plategaPaymentMethod = null) => {
    if (!selectedTariffId) return;
    
    setLoadingTariffId(selectedTariffId);
    setError(null);
    setShowPaymentModal(false);
    
    try {
      const response = await fetch('/api/client/create-payment', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ 
          tariff_id: selectedTariffId,
          promo_code: appliedPromo && appliedPromo.type === 'PERCENT' ? appliedPromo.code : null,
          payment_provider: paymentProvider,
          ...(paymentProvider === 'platega' && plategaPaymentMethod ? { platega_payment_method: plategaPaymentMethod } : {})
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || 'Ошибка создания счета');
      window.location.href = data.payment_url;
    } catch (e) {
      setError(e.message);
      setLoadingTariffId(null);
      setShowPaymentModal(true); // Показываем модалку снова при ошибке
    }
  };

  // Группируем тарифы по уровням (должно быть до условного возврата)
  const groupedTariffs = useMemo(() => {
    const groups = {
      basic: [],
      pro: [],
      elite: []
    };
    
    tariffs.forEach(tariff => {
      const tier = getTier(tariff);
      if (groups[tier]) {
        groups[tier].push(tariff);
      }
    });
    
    // Сортируем тарифы в каждой группе по длительности (от меньшего к большему)
    Object.keys(groups).forEach(tier => {
      groups[tier].sort((a, b) => (a.duration_days || 0) - (b.duration_days || 0));
    });
    
    return groups;
  }, [tariffs]);

  if (loading) return <div className="loading-mini">Загружаем тарифы…</div>;

  const calculatePriceWithDiscount = (tariff) => {
    const price = formatPrice(tariff);
    if (appliedPromo && appliedPromo.type === 'PERCENT') {
      const discount = (appliedPromo.value / 100) * price.value;
      const finalPrice = price.value - discount;
      const config = currencyConfig[currency] || currencyConfig.uah;
      const intlFormatter = new Intl.NumberFormat('ru-RU', {
        style: 'currency',
        currency: config.code,
        maximumFractionDigits: 0
      });
      return {
        original: price.formatted,
        discounted: intlFormatter.format(finalPrice),
        discount: appliedPromo.value
      };
    }
    return null;
  };

  const renderTariffCard = (tariff) => {
    const isLoading = loadingTariffId === tariff.id;
    const tier = getTier(tariff);
    const price = formatPrice(tariff);
    const discountInfo = calculatePriceWithDiscount(tariff);
    return (
      <article key={tariff.id} className={`tariff-card ${tier} ${tier !== 'basic' ? 'featured' : ''}`}>
        {tariff.badge && tariff.badge.trim() !== '' && (
          <span className="tariff-ribbon" title={t(`tariffs.badge.${tariff.badge}`, 'ТОП продаж')}>
            {t(`tariffs.badge.${tariff.badge}`, 'ТОП продаж')}
          </span>
        )}
        <p className="tariff-label">{t(`tariffs.tier.${tier}`, tier === 'basic' ? 'Базовый' : tier === 'pro' ? 'Премиум' : 'Элитный')}</p>
        <h3>{translateTariffName(t(`tariffs.${tariff.name}`, tariff.name), tariff.duration_days, i18n.resolvedLanguage || 'ru')}</h3>
        <div className="tariff-price">
          {discountInfo ? (
            <>
              <span style={{ textDecoration: 'line-through', opacity: 0.6, marginRight: '8px' }}>
                {discountInfo.original}
              </span>
              <span style={{ color: 'var(--accent-primary)', fontWeight: 'bold' }}>
                {discountInfo.discounted}
              </span>
              <span style={{ fontSize: '0.8em', color: 'var(--accent-primary)', marginLeft: '8px' }}>
                -{discountInfo.discount}%
              </span>
            </>
          ) : (
            price.formatted
          )}
          <span>/ {tariff.duration_days} {getDaysText(tariff.duration_days, i18n.resolvedLanguage || 'ru')}</span>
        </div>
        <div className="tariff-meta">
          <div>
            <span>Цена за день</span>
            <strong>{price.perDayFormatted}</strong>
          </div>
          <div>
            <span>Бонус</span>
            <strong>{tier === 'elite' ? '+15 дней' : '+7 дней'}</strong>
          </div>
        </div>
        <ul className="tariff-features">
          {(features[tier] && features[tier].length > 0 ? features[tier] : (featurePresets[tier] || [])).map((feature, idx) => (
            <li key={`${tier}-${idx}-${feature}`}>{feature}</li>
          ))}
        </ul>
        <button
          className="btn btn-primary"
          onClick={() => handleSelectTariff(tariff.id)}
          disabled={isLoading}
        >
          {isLoading ? 'Создаем счёт…' : t('tariffs.select')}
        </button>
      </article>
    );
  };

  return (
    <div className="tariffs-container">
      {error && <div className="message-error">{error}</div>}
      
      {/* Промокод */}
      <div className="promo-code-section">
        <h3 style={{ marginTop: 0, marginBottom: '15px' }}>Промокод</h3>
        <div className="promo-code-input-wrapper">
          <input
            type="text"
            value={promoCode}
            onChange={(e) => setPromoCode(e.target.value.toUpperCase())}
            placeholder="Введите промокод"
            className="promo-code-input"
            onKeyPress={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handleApplyPromo();
              }
            }}
          />
          <button
            onClick={handleApplyPromo}
            className="btn promo-code-button"
          >
            Применить
          </button>
        </div>
        {promoError && (
          <div style={{ marginTop: '10px', color: 'var(--accent-red)', fontSize: '14px' }}>
            {promoError}
          </div>
        )}
        {appliedPromo && appliedPromo.type === 'PERCENT' && (
          <div style={{ marginTop: '10px', color: 'var(--accent-primary)', fontSize: '14px', fontWeight: '600' }}>
            ✓ Промокод {appliedPromo.code} применен! Скидка {appliedPromo.value}%
          </div>
        )}
      </div>
      
      {/* Базовые тарифы - 1 строка */}
      {groupedTariffs.basic.length > 0 && (
        <div className="tariff-tier-section">
          <h3 className="tariff-tier-title">{t('tariffs.tier.basic', 'Базовый')}</h3>
          <div className="tariff-grid modern">
            {groupedTariffs.basic.map(renderTariffCard)}
          </div>
        </div>
      )}
      
      {/* Премиум тарифы - 2 строка */}
      {groupedTariffs.pro.length > 0 && (
        <div className="tariff-tier-section">
          <h3 className="tariff-tier-title">{t('tariffs.tier.pro', 'Премиум')}</h3>
          <div className="tariff-grid modern">
            {groupedTariffs.pro.map(renderTariffCard)}
          </div>
        </div>
      )}
      
      {/* Элитные тарифы - 3 строка */}
      {groupedTariffs.elite.length > 0 && (
        <div className="tariff-tier-section">
          <h3 className="tariff-tier-title">{t('tariffs.tier.elite', 'Элитный')}</h3>
          <div className="tariff-grid modern">
            {groupedTariffs.elite.map(renderTariffCard)}
          </div>
        </div>
      )}

      {/* Модальное окно выбора способа оплаты - рендерим через Portal в document.body */}
      {showPaymentModal && createPortal(
        <div 
          className="modal-overlay payment-modal-overlay" 
          onClick={() => setShowPaymentModal(false)}
        >
          <div 
            className="modal-content payment-modal-content"
            onClick={(e) => e.stopPropagation()}
          >
            <h3>Выберите способ оплаты</h3>
            <div className="payment-methods-list">
              <button
                className="btn btn-primary"
                onClick={() => handleCreatePayment('crystalpay')}
                disabled={loadingTariffId === selectedTariffId}
              >
                {loadingTariffId === selectedTariffId ? 'Создаем счёт…' : 'CrystalPay'}
              </button>
              <button
                className="btn btn-primary"
                onClick={() => handleCreatePayment('heleket')}
                disabled={loadingTariffId === selectedTariffId}
              >
                {loadingTariffId === selectedTariffId ? 'Создаем счёт…' : 'Heleket (Криптовалюты)'}
              </button>
              {Array.isArray(plategaMethods) && plategaMethods.length > 0 ? (
                <div className="platega-methods-list" style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {plategaMethods.map((m) => (
                    <button
                      key={`platega-${m}`}
                      className="btn btn-primary"
                      onClick={() => handleCreatePayment('platega', m)}
                      disabled={loadingTariffId === selectedTariffId}
                      style={{ width: '100%' }}
                    >
                      {loadingTariffId === selectedTariffId ? 'Создаем счёт…' : (PLATEGA_METHOD_LABELS[m] || `Platega ${m}`)}
                    </button>
                  ))}
                </div>
              ) : (
                <button
                  className="btn btn-primary"
                  onClick={() => handleCreatePayment('platega')}
                  disabled={loadingTariffId === selectedTariffId}
                >
                  {loadingTariffId === selectedTariffId ? 'Создаем счёт…' : 'Platega'}
                </button>
              )}
              <div style={{ width: '100%' }}>
                <button
                  className="btn btn-primary"
                  onClick={() => handleCreatePayment('telegram_stars')}
                  disabled={loadingTariffId === selectedTariffId}
                  style={{ width: '100%' }}
                >
                  {loadingTariffId === selectedTariffId ? 'Создаем счёт…' : 'Telegram Stars ⭐'}
                </button>
                <p style={{ 
                  fontSize: '12px', 
                  color: 'var(--text-secondary)', 
                  margin: '4px 0 0 0',
                  textAlign: 'center'
                }}>
                  Подойдет для жителей Украины
                </p>
              </div>
              <button
                className="btn payment-cancel-button"
                onClick={() => {
                  setShowPaymentModal(false);
                  setSelectedTariffId(null);
                }}
                disabled={loadingTariffId === selectedTariffId}
              >
                Отмена
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
};

export default function ClientTariffsPage() {
  const { t } = useTranslation();
  return (
    <main className="client-page-content">
      <section className="tariff-hero glass-card gradient-card">
        <div>
          <p className="eyebrow-text">{t('dashboard.tariffs')}</p>
          <h2>Премиум VPN без лимитов</h2>
          <p>Выберите срок подписки и мгновенно получите доступ к всем серверам и новому ключу подключения.</p>
        </div>
        <ul className="tariff-hero-stats">
          <li><span>5+</span> способов оплаты</li>
          <li><span>24/7</span> поддержка</li>
          <li><span>∞</span> трафик</li>
        </ul>
      </section>

      <section className="tariffs-section">
        <TariffSection />
      </section>
    </main>
  );
}

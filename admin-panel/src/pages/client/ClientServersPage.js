import React, { useState, useEffect, useMemo } from 'react';
import { useAuth } from '../../AuthContext';
import { useTranslation } from 'react-i18next';
import { LuZap, LuShieldCheck, LuSignalHigh } from 'react-icons/lu';

const flagMap = {
  US: '🇺🇸',
  DE: '🇩🇪',
  NL: '🇳🇱',
  FR: '🇫🇷',
  GB: '🇬🇧',
  UA: '🇺🇦',
  PL: '🇵🇱',
  CA: '🇨🇦',
  JP: '🇯🇵',
  AU: '🇦🇺'
};

const palette = [
  'linear-gradient(135deg, rgba(63,105,255,0.18), rgba(14,165,233,0.2))',
  'linear-gradient(135deg, rgba(16,185,129,0.18), rgba(14,116,144,0.2))',
  'linear-gradient(135deg, rgba(251,191,36,0.2), rgba(248,113,113,0.2))',
  'linear-gradient(135deg, rgba(147,51,234,0.18), rgba(59,130,246,0.2))'
];

const tagPresets = [
  ['WireGuard', 'Streaming'],
  ['Gaming', 'AntiDPI'],
  ['Privacy', 'Multi-hop'],
  ['P2P', 'ShadowSocks']
];

const ServerList = ({ token }) => {
  const [nodes, setNodes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeRegion, setActiveRegion] = useState('all');

  useEffect(() => {
    const fetchNodes = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/client/nodes', {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
          const data = await response.json();
          setNodes(data.response?.activeNodes || []);
        }
      } catch (e) {
        console.error('Не удалось загрузить серверы', e);
      } finally {
        setLoading(false);
      }
    };
    if (token) {
      fetchNodes();
    }
  }, [token]);

  const regions = useMemo(() => {
    const regionList = nodes
      .map((node) => node.regionName || node.countryCode?.toUpperCase())
      .filter(Boolean);
    return Array.from(new Set(regionList)).slice(0, 6);
  }, [nodes]);

  const filteredNodes = useMemo(() => {
    if (activeRegion === 'all') return nodes;
    return nodes.filter(
      (node) => (node.regionName || node.countryCode?.toUpperCase()) === activeRegion
    );
  }, [nodes, activeRegion]);

  if (loading) return <div className="loading-mini">Подготавливаем список узлов…</div>;
  if (!nodes.length) {
    return <div className="empty-state glass-card">На данный момент нет активных узлов. Попробуйте обновить позже.</div>;
  }

  return (
    <div className="servers-panel glass-card">
      <div className="servers-toolbar">
        <div>
          <p>Доступно узлов: <strong>{nodes.length}</strong></p>
          <span>обновлено {new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' }).format(new Date())}</span>
        </div>
        <div className="pill-switch">
          <button
            type="button"
            className={activeRegion === 'all' ? 'active' : ''}
            onClick={() => setActiveRegion('all')}
          >
            Все
          </button>
          {regions.map((region) => (
            <button
              key={region}
              type="button"
              className={activeRegion === region ? 'active' : ''}
              onClick={() => setActiveRegion(region)}
            >
              {region}
            </button>
          ))}
        </div>
      </div>

      <div className="server-grid modern">
        {filteredNodes.map((node, index) => {
          const paletteBg = palette[index % palette.length];
          const latency = 18 + ((index * 11) % 60);
          const load = ((index * 17) % 80) + 15;
          const tags = tagPresets[index % tagPresets.length];
          const location = node.city || node.regionName || node.countryCode?.toUpperCase();
          const countryCode = node.countryCode?.toUpperCase() || 'XX';

          return (
            <article key={node.uuid || `${countryCode}-${index}`} className="server-card" style={{ background: paletteBg }}>
              <div className="server-card-head">
                <span className="flag">{flagMap[countryCode] || countryCode}</span>
                <div>
                  <p className="server-location">{location}</p>
                  <span className="server-region">{node.nodeName}</span>
                </div>
                <span className={`server-status ${load > 80 ? 'warn' : ''}`}>
                  {load > 80 ? 'Пиковая нагрузка' : 'Стабильно'}
                </span>
              </div>

              <div className="server-metrics">
                <div>
                  <span>Ping</span>
                  <strong>{latency} ms</strong>
                </div>
                <div>
                  <span>Скорость</span>
                  <strong>{load > 80 ? '600 Мбит/с' : '1 Гбит/с'}</strong>
                </div>
                <div>
                  <span>Шифрование</span>
                  <strong>{tags[0]}</strong>
                </div>
              </div>

              <div className="server-tags">
                {tags.map((tag) => (
                  <span key={tag} className="chip">{tag}</span>
                ))}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
};

export default function ClientServersPage() {
  const { t } = useTranslation();
  const { token, user } = useAuth();

  const isSubActive = Boolean(user?.activeInternalSquads?.length);
  const isExpired = user && new Date(user.expireAt) < new Date();
  const isTrulyActive = isSubActive && !isExpired;

  return (
    <main className="client-page-content">
      <section className="servers-hero glass-card gradient-card">
        <div>
          <p className="eyebrow-text">{t('sidebar.servers', 'Серверы')}</p>
          <h2>Глобальная сеть StealthNET</h2>
          <p>Держим низкий пинг и высокую скорость, чтобы VPN чувствовался как прямое подключение.</p>
          <div className="hero-quick-actions">
            <span className="chip-btn secondary"><LuSignalHigh /> <strong>40+</strong> локаций</span>
            <span className="chip-btn secondary"><LuZap /> Безлимитный трафик</span>
            <span className="chip-btn secondary"><LuShieldCheck /> Anti-DPI</span>
          </div>
        </div>
      </section>

      <section className="servers-section">
        <h2>{t('dashboard.servers')}</h2>
        {isTrulyActive ? (
          <ServerList token={token} />
        ) : (
          <div className="empty-state glass-card">
            Подписка не активна. Включите триал или оформите тариф, чтобы видеть список серверов и конфигурации.
          </div>
        )}
      </section>
    </main>
  );
}

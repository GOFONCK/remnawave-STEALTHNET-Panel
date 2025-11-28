import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import HttpApi from 'i18next-http-backend';

i18n
  // 1. Загрузка переводов (из /public/locales)
  .use(HttpApi)
  // 2. Определение языка браузера
  .use(LanguageDetector)
  // 3. Передача i18n в react
  .use(initReactI18next)
  .init({
    // 4. Язык по умолчанию
    fallbackLng: 'ru',
    debug: true, // Включить логи в консоли
    
    // 5. Языки, которые мы поддерживаем
    supportedLngs: ['ru', 'ua', 'cn', 'en'],

    interpolation: {
      escapeValue: false, // не нужно для React
    },
    
    // 6. Настройки детектора языка
    detection: {
      // Порядок: 1. из localStorage, 2. из URL, 3. из браузера
      order: ['localStorage', 'querystring', 'navigator'],
      caches: ['localStorage'], // Где сохранять выбор
    },
    
    // 7. Путь к файлам переводов
    backend: {
      loadPath: '/locales/{{lng}}/translation.json',
    },
  });

export default i18n;
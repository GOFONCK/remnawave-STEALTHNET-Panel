import React, { useState } from 'react';
import { useAuth } from '../AuthContext';
import { useNavigate } from 'react-router-dom';

function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const { login } = useAuth(); // Берем функцию "login" из нашего Контекста
  const navigate = useNavigate(); // Для переадресации

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      // Вызываем нашу функцию login из AuthContext
      await login(email, password);
      // Если login прошел успешно (не выкинул ошибку),
      // переадресуем в личный кабинет
      navigate('/dashboard');
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
    // setLoading(false) не нужен при успехе, т.к. мы уходим со страницы
  };

  return (
    <div className="container">
      <h2>Вход для клиентов</h2>
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="email">Email:</label>
          <input
            type="email"
            id="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            disabled={loading}
          />
        </div>
        <div className="form-group">
          <label htmlFor="password">Пароль:</label>
          <input
            type="password"
            id="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            disabled={loading}
          />
        </div>

        {/* Показываем ошибку, если она есть */}
        {error && (
          <div id="message" className="message-error">
            {error}
          </div>
        )}

        <button type="submit" className="btn" disabled={loading}>
          {loading ? 'Вход...' : 'Войти'}
        </button>
      </form>
      {/* TODO: Добавить ссылку на /register
        <p>Нет аккаунта? <Link to="/register">Зарегистрироваться</Link></p> 
      */}
    </div>
  );
}

export default LoginPage;
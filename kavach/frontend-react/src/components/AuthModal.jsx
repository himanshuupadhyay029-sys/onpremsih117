import React, { useState } from 'react';

const API_BASE = '';

export default function AuthModal({ onClose, onAuthSuccess }) {
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const switchMode = () => {
    setMode((prev) => (prev === 'login' ? 'register' : 'login'));
    setError('');
  };

  const validate = () => {
    if (!email.trim() || !password) {
      setError('Email and password are required.');
      return false;
    }
    if (mode === 'register') {
      if (!name.trim()) {
        setError('Name is required.');
        return false;
      }
      if (password.length < 6) {
        setError('Password must be at least 6 characters.');
        return false;
      }
      if (password !== confirmPassword) {
        setError('Passwords do not match.');
        return false;
      }
    }
    return true;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate()) return;
    setLoading(true);
    setError('');

    const url =
      mode === 'login'
        ? `${API_BASE}/auth/login`
        : `${API_BASE}/auth/register`;

    const body =
      mode === 'login'
        ? { email: email.trim().toLowerCase(), password }
        : { name: name.trim(), email: email.trim().toLowerCase(), password };

    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(body),
      });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || `Error ${res.status}`);
      }

      if (mode === 'register') {
        // After register, auto-login
        const loginRes = await fetch(`${API_BASE}/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({
            email: email.trim().toLowerCase(),
            password,
          }),
        });
        const loginData = await loginRes.json();
        if (!loginRes.ok) {
          throw new Error(loginData.detail || 'Login after registration failed.');
        }
        onAuthSuccess(loginData);
      } else {
        onAuthSuccess(data);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div className="auth-overlay" onClick={handleOverlayClick} id="auth-overlay">
      <div className="auth-modal" id="auth-modal">
        <button
          className="auth-close-btn"
          onClick={onClose}
          title="Close"
          aria-label="Close auth modal"
          id="auth-close-btn"
        >
          <svg className="icon" viewBox="0 0 24 24">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        </button>

        <div className="auth-header">
          <svg className="auth-shield-icon" viewBox="0 0 24 24">
            <path d="M12 3l7 3v5.5c0 4.2-2.9 8.1-7 9.5-4.1-1.4-7-5.3-7-9.5V6l7-3z" />
          </svg>
          <h2 className="auth-title">
            {mode === 'login' ? 'Welcome back' : 'Create account'}
          </h2>
          <p className="auth-subtitle">
            {mode === 'login'
              ? 'Sign in to access your sovereign workspace'
              : 'Register to start using KAVACH'}
          </p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit} id="auth-form">
          {mode === 'register' && (
            <div className="auth-field">
              <label className="auth-label" htmlFor="auth-name">Name</label>
              <input
                className="auth-input"
                type="text"
                id="auth-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                autoComplete="name"
              />
            </div>
          )}

          <div className="auth-field">
            <label className="auth-label" htmlFor="auth-email">Email</label>
            <input
              className="auth-input"
              type="email"
              id="auth-email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              autoComplete="email"
              autoFocus
            />
          </div>

          <div className="auth-field">
            <label className="auth-label" htmlFor="auth-password">Password</label>
            <input
              className="auth-input"
              type="password"
              id="auth-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            />
          </div>

          {mode === 'register' && (
            <div className="auth-field">
              <label className="auth-label" htmlFor="auth-confirm-password">
                Confirm Password
              </label>
              <input
                className="auth-input"
                type="password"
                id="auth-confirm-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="new-password"
              />
            </div>
          )}

          {error && (
            <div className="auth-error" id="auth-error">
              <svg className="icon icon-sm" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 8v4M12 16h.01" />
              </svg>
              <span>{error}</span>
            </div>
          )}

          <button
            className="auth-submit-btn"
            type="submit"
            disabled={loading}
            id="auth-submit-btn"
          >
            {loading ? (
              <span className="auth-spinner" />
            ) : mode === 'login' ? (
              'Sign In'
            ) : (
              'Create Account'
            )}
          </button>
        </form>

        <div className="auth-switch">
          <span>
            {mode === 'login'
              ? "Don't have an account?"
              : 'Already have an account?'}
          </span>
          <button
            className="auth-switch-btn"
            onClick={switchMode}
            id="auth-switch-btn"
          >
            {mode === 'login' ? 'Register' : 'Sign In'}
          </button>
        </div>
      </div>
    </div>
  );
}

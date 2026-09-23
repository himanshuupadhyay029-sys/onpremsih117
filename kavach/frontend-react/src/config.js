// Central configuration for KAVACH frontend

export const API_BASE =
  import.meta.env.VITE_API_BASE ||
  (typeof window !== 'undefined' &&
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? ''
    : 'https://kavach-backend-3vm9.onrender.com');

export const IS_CLOUD =
  import.meta.env.VITE_CLOUD_DEPLOYMENT === 'true' ||
  (typeof window !== 'undefined' &&
    window.location.hostname !== 'localhost' &&
    window.location.hostname !== '127.0.0.1');

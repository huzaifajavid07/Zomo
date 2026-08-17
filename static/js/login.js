/**
 * Zomo Login Module
 * Authenticates users via backend API /api/auth/login
 */

const AUTH_KEY = 'zomo_admin_auth';
const TOKEN_KEY = 'authToken';

function redirectToDashboard() {
  window.location.href = '/';
}

function setAuth(user, token) {
  const session = {
    id: user.id,
    email: user.email,
    name: user.name || 'User',
    role: (user.role === 'superadmin' || user.role === 'admin') ? 'superadmin' : 'user',
    loggedInAt: new Date().toISOString()
  };
  localStorage.setItem(AUTH_KEY, JSON.stringify(session));
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  }
}

function getAuth() {
  const raw = localStorage.getItem(AUTH_KEY);
  return raw ? JSON.parse(raw) : null;
}

function checkExistingSession() {
  const auth = getAuth();
  if (auth) {
    redirectToDashboard();
  }
}

function showError(message) {
  const errorNode = document.getElementById('loginError');
  if (!errorNode) return;
  errorNode.textContent = message;
  errorNode.style.display = message ? 'block' : 'none';
}

async function handleLoginSubmit(event) {
  event.preventDefault();
  showError('');

  const emailInput = document.getElementById('email');
  const passwordInput = document.getElementById('password');
  const submitBtn = event.target.querySelector('button[type="submit"]');

  const email = emailInput ? emailInput.value.trim() : '';
  const password = passwordInput ? passwordInput.value.trim() : '';

  if (!email || !password) {
    showError('Please enter both email and password.');
    return;
  }

  const originalBtnText = submitBtn ? submitBtn.innerText : 'Login';
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.innerText = 'Authenticating...';
  }

  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });

    const data = await response.json();

    if (response.ok && data.status === 'ok') {
      setAuth(data.user, data.token);
      redirectToDashboard();
    } else {
      showError(data.message || 'Invalid email or password.');
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerText = originalBtnText;
      }
    }
  } catch (err) {
    console.warn('Backend login request error:', err);
    // Fallback for offline demo mode
    if (email.toLowerCase() === 'admin@example.com' && password === 'admin123') {
      setAuth({ id: '1', email, name: 'Admin User', role: 'admin' }, 'demo_token');
      redirectToDashboard();
    } else {
      showError('Connection error or invalid credentials. Please try again.');
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerText = originalBtnText;
      }
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  checkExistingSession();

  const form = document.getElementById('loginForm');
  if (form) {
    form.addEventListener('submit', handleLoginSubmit);
  }
});

/* ═══════════════════════════════════════════════════════════════ */
/* SHARED UTILITIES & HELPERS */
/* ═══════════════════════════════════════════════════════════════ */

/**
 * API Communication
 */
class ApiClient {
    constructor(baseURL = '/api') {
        this.baseURL = baseURL;
    }

    async get(endpoint) {
        try {
            const response = await fetch(`${this.baseURL}${endpoint}`, {
                method: 'GET',
                headers: this.getHeaders()
            });
            return this.handleResponse(response);
        } catch (error) {
            console.error('API GET Error:', error);
            throw error;
        }
    }

    async post(endpoint, data) {
        try {
            const response = await fetch(`${this.baseURL}${endpoint}`, {
                method: 'POST',
                headers: this.getHeaders(),
                body: JSON.stringify(data)
            });
            return this.handleResponse(response);
        } catch (error) {
            console.error('API POST Error:', error);
            throw error;
        }
    }

    async put(endpoint, data) {
        try {
            const response = await fetch(`${this.baseURL}${endpoint}`, {
                method: 'PUT',
                headers: this.getHeaders(),
                body: JSON.stringify(data)
            });
            return this.handleResponse(response);
        } catch (error) {
            console.error('API PUT Error:', error);
            throw error;
        }
    }

    async delete(endpoint) {
        try {
            const response = await fetch(`${this.baseURL}${endpoint}`, {
                method: 'DELETE',
                headers: this.getHeaders()
            });
            return this.handleResponse(response);
        } catch (error) {
            console.error('API DELETE Error:', error);
            throw error;
        }
    }

    getHeaders() {
        return getAuthHeaders();
    }

    getToken() {
        return localStorage.getItem('authToken') || '';
    }

    async handleResponse(response) {
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.message || 'API request failed');
        }
        return data;
    }
}

/**
 * Standard Auth Headers for Fetch Calls
 */
function getAuthHeaders(customHeaders = {}) {
    const raw = localStorage.getItem('zomo_admin_auth');
    const auth = raw ? JSON.parse(raw) : null;
    const token = localStorage.getItem('authToken') || '';

    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        ...customHeaders
    };

    if (auth) {
        if (auth.id) headers['x-user-id'] = String(auth.id);
        if (auth.email) headers['x-user-email'] = String(auth.email);
        if (auth.role) headers['x-user-role'] = String(auth.role);
    }
    return headers;
}

window.getAuthHeaders = getAuthHeaders;

/**
 * Local Storage Manager
 */
class StorageManager {
    static set(key, value) {
        try {
            localStorage.setItem(key, JSON.stringify(value));
        } catch (error) {
            console.error('Storage set error:', error);
        }
    }

    static get(key) {
        try {
            const item = localStorage.getItem(key);
            return item ? JSON.parse(item) : null;
        } catch (error) {
            console.error('Storage get error:', error);
            return null;
        }
    }

    static remove(key) {
        try {
            localStorage.removeItem(key);
        } catch (error) {
            console.error('Storage remove error:', error);
        }
    }

    static clear() {
        try {
            localStorage.clear();
        } catch (error) {
            console.error('Storage clear error:', error);
        }
    }
}

/**
 * Date/Time Utilities
 */
class DateUtils {
    static formatDate(date, format = 'MM/DD/YYYY') {
        const d = new Date(date);
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        const year = d.getFullYear();

        return format
            .replace('MM', month)
            .replace('DD', day)
            .replace('YYYY', year);
    }

    static formatTime(date, format = 'HH:mm:ss') {
        const d = new Date(date);
        const hours = String(d.getHours()).padStart(2, '0');
        const minutes = String(d.getMinutes()).padStart(2, '0');
        const seconds = String(d.getSeconds()).padStart(2, '0');

        return format
            .replace('HH', hours)
            .replace('mm', minutes)
            .replace('ss', seconds);
    }

    static getRelativeTime(date) {
        const now = new Date();
        const diff = now - new Date(date);
        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);

        if (days > 0) return `${days} day${days > 1 ? 's' : ''} ago`;
        if (hours > 0) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
        if (minutes > 0) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
        return 'just now';
    }
}

/**
 * String Utilities
 */
class StringUtils {
    static capitalize(str) {
        return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
    }

    static titleCase(str) {
        return str.split(' ').map(word => this.capitalize(word)).join(' ');
    }

    static truncate(str, length = 50) {
        return str.length > length ? str.substring(0, length) + '...' : str;
    }

    static slugify(str) {
        return str
            .toLowerCase()
            .trim()
            .replace(/[^\w\s-]/g, '')
            .replace(/[\s_-]+/g, '-')
            .replace(/^-+|-+$/g, '');
    }

    static camelCase(str) {
        return str
            .replace(/(?:^\w|[A-Z]|\b\w)/g, (word, index) => 
                index === 0 ? word.toLowerCase() : word.toUpperCase()
            )
            .replace(/\s+/g, '');
    }
}

/**
 * Number Utilities
 */
class NumberUtils {
    static formatCurrency(value, currency = 'USD') {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: currency
        }).format(value);
    }

    static formatNumber(value, decimals = 0) {
        return Number(value).toLocaleString('en-US', {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals
        });
    }

    static formatBytes(bytes) {
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        if (bytes === 0) return '0 B';

        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(2) + ' ' + sizes[i];
    }

    static calculatePercentage(value, total) {
        return ((value / total) * 100).toFixed(2) + '%';
    }
}

/**
 * Validation Utilities
 */
class ValidationUtils {
    static isEmail(email) {
        const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return regex.test(email);
    }

    static isPhone(phone) {
        const regex = /^[\+]?[(]?[0-9]{3}[)]?[-\s\.]?[0-9]{3}[-\s\.]?[0-9]{4,6}$/;
        return regex.test(phone);
    }

    static isUrl(url) {
        try {
            new URL(url);
            return true;
        } catch {
            return false;
        }
    }

    static isStrongPassword(password) {
        // At least 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special char
        const regex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$/;
        return regex.test(password);
    }

    static isEmpty(value) {
        return value === null || value === undefined || value === '';
    }
}

/**
 * Event Bus for component communication
 */
class EventBus {
    constructor() {
        this.events = {};
    }

    on(event, callback) {
        if (!this.events[event]) {
            this.events[event] = [];
        }
        this.events[event].push(callback);
    }

    off(event, callbackToRemove) {
        if (this.events[event]) {
            this.events[event] = this.events[event].filter(
                callback => callback !== callbackToRemove
            );
        }
    }

    emit(event, data) {
        if (this.events[event]) {
            this.events[event].forEach(callback => callback(data));
        }
    }

    once(event, callback) {
        const oneTimeCallback = (data) => {
            callback(data);
            this.off(event, oneTimeCallback);
        };
        this.on(event, oneTimeCallback);
    }
}

/**
 * Debounce function
 */
function debounce(func, wait = 300) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

/**
 * Throttle function
 */
function throttle(func, limit = 300) {
    let lastFunc;
    let lastRan;
    return function(...args) {
        if (!lastRan) {
            func.apply(this, args);
            lastRan = Date.now();
        } else {
            clearTimeout(lastFunc);
            lastFunc = setTimeout(() => {
                if (Date.now() - lastRan >= limit) {
                    func.apply(this, args);
                    lastRan = Date.now();
                }
            }, limit - (Date.now() - lastRan));
        }
    };
}

/**
 * Deep clone object
 */
function deepClone(obj) {
    if (obj === null || typeof obj !== 'object') return obj;
    if (obj instanceof Date) return new Date(obj.getTime());
    if (obj instanceof Array) return obj.map(item => deepClone(item));
    if (obj instanceof Object) {
        const clonedObj = {};
        for (const key in obj) {
            if (obj.hasOwnProperty(key)) {
                clonedObj[key] = deepClone(obj[key]);
            }
        }
        return clonedObj;
    }
}

/**
 * Merge objects
 */
function mergeObjects(target, source) {
    for (const key in source) {
        if (source.hasOwnProperty(key)) {
            if (typeof source[key] === 'object' && source[key] !== null) {
                target[key] = mergeObjects(target[key] || {}, source[key]);
            } else {
                target[key] = source[key];
            }
        }
    }
    return target;
}
/**
 * Theme Management (Dark / Light Mode)
 */
class ThemeManager {
    static getTheme() {
        return localStorage.getItem('zomo_theme') || 'dark';
    }

    static setTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('zomo_theme', theme);
        ThemeManager.updateToggleButton(theme);
    }

    static toggleTheme() {
        const current = ThemeManager.getTheme();
        const next = current === 'dark' ? 'light' : 'dark';
        ThemeManager.setTheme(next);
        return next;
    }

    static updateToggleButton(theme) {
        const btns = document.querySelectorAll('[data-action="toggle-theme"], #themeToggleBtn');
        btns.forEach(btn => {
            if (theme === 'dark') {
                btn.innerHTML = '☀️ <span class="theme-text">Light Mode</span>';
                btn.setAttribute('title', 'Switch to Light Mode');
                btn.setAttribute('aria-label', 'Switch to Light Mode');
            } else {
                btn.innerHTML = '🌙 <span class="theme-text">Dark Mode</span>';
                btn.setAttribute('title', 'Switch to Dark Mode');
                btn.setAttribute('aria-label', 'Switch to Dark Mode');
            }
        });
    }

    static init() {
        const theme = ThemeManager.getTheme();
        ThemeManager.setTheme(theme);
    }
}

// Global toggle helper
function toggleTheme() {
    return ThemeManager.toggleTheme();
}

window.toggleTheme = toggleTheme;
window.ThemeManager = ThemeManager;

// Auto-run immediately to prevent theme flash
ThemeManager.init();

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        ThemeManager.updateToggleButton(ThemeManager.getTheme());
    });
} else {
    ThemeManager.updateToggleButton(ThemeManager.getTheme());
}

// Export for use in modules (if using module system)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        ApiClient,
        StorageManager,
        DateUtils,
        StringUtils,
        NumberUtils,
        ValidationUtils,
        EventBus,
        ThemeManager,
        toggleTheme,
        debounce,
        throttle,
        deepClone,
        mergeObjects
    };
}

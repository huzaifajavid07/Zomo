/* ═══════════════════════════════════════════════════════════════ */
/* ANALYTICS & CHART UTILITIES */
/* ═══════════════════════════════════════════════════════════════ */

class AnalyticsManager {
    constructor() {
        this.charts = {};
        this.data = {
            daily: [],
            hourly: [],
            byStatus: {
                active: 5,
                queued: 1,
                completed: 2,
                failed: 0
            }
        };
    }

    /**
     * Initialize analytics dashboard
     */
    init() {
        this.loadData();
        this.setupCharts();
        this.attachEventListeners();
    }

    /**
     * Load analytics data
     */
    loadData() {
        this.data.daily = this.generateDailyData();
        this.data.hourly = this.generateHourlyData();
    }

    /**
     * Generate simulated daily data
     */
    generateDailyData() {
        const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
        return days.map(day => ({
            day,
            bots: Math.floor(Math.random() * 100) + 20,
            meetings: Math.floor(Math.random() * 20) + 5
        }));
    }

    /**
     * Generate simulated hourly data
     */
    generateHourlyData() {
        const hours = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`);
        return hours.map(hour => ({
            hour,
            count: Math.floor(Math.random() * 50) + 10
        }));
    }

    /**
     * Setup all charts
     */
    setupCharts() {
        // Status chart can be initialized or updated here
    }

    /**
     * Update chart data dynamically
     */
    updateChartData(chartName, newData) {
        if (this.charts[chartName]) {
            this.charts[chartName].data.datasets[0].data = newData;
            this.charts[chartName].update('active');
        }
    }

    /**
     * Get statistics summary
     */
    getStatsSummary() {
        const total = Object.values(this.data.byStatus).reduce((a, b) => a + b, 0) || 1;
        const active = this.data.byStatus.active || 0;
        const completed = this.data.byStatus.completed || 0;

        return {
            total,
            active,
            completed,
            activePct: ((active / total) * 100).toFixed(1),
            completedPct: ((completed / total) * 100).toFixed(1)
        };
    }

    /**
     * Export analytics data as JSON
     */
    exportData() {
        return JSON.stringify(this.data, null, 2);
    }

    /**
     * Attach event listeners
     */
    attachEventListeners() {}
}

// Initialize Analytics Manager
const analyticsManager = new AnalyticsManager();

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        analyticsManager.init();
    });
} else {
    analyticsManager.init();
}

/**
 * Utility: Format large numbers with commas
 */
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/**
 * Utility: Format percentage with rounding
 */
function formatPercentage(value, total) {
    return ((value / total) * 100).toFixed(1) + '%';
}

/**
 * Utility: Get time-formatted string
 */
function getFormattedTime(date = new Date()) {
    return date.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true
    });
}

/**
 * Utility: Get date-formatted string
 */
function getFormattedDate(date = new Date()) {
    return date.toLocaleDateString('en-US', {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
}

/**
 * Utility: Calculate time difference
 */
function getTimeDifference(start, end) {
    const diff = end - start;
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) return `${hours}h ${minutes % 60}m`;
    if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
    return `${seconds}s`;
}

/**
 * Chart color scheme
 */
const chartColors = {
    primary: '#3b82f6',
    success: '#10b981',
    warning: '#f59e0b',
    danger: '#ef4444',
    info: '#06b6d4',
    secondary: '#8b5cf6'
};

/**
 * Status badge mapping
 */
const statusBadges = {
    active: { color: '#10b981', label: 'Active', icon: '●' },
    queued: { color: '#f59e0b', label: 'Queued', icon: '⟳' },
    completed: { color: '#3b82f6', label: 'Completed', icon: '✓' },
    failed: { color: '#ef4444', label: 'Failed', icon: '✕' },
    idle: { color: '#64748b', label: 'Idle', icon: '○' }
};

/**
 * Create a status badge element
 */
function createStatusBadge(status) {
    const badge = statusBadges[status] || statusBadges.idle;
    const element = document.createElement('span');
    element.className = `badge badge-${status}`;
    element.style.color = badge.color;
    element.innerHTML = `<span class="status-icon">${badge.icon}</span> ${badge.label}`;
    return element;
}

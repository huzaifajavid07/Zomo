/* ═══════════════════════════════════════════════════════════════ */
/* DASHBOARD LOGIC & INTERACTIONS — USER ISOLATED */
/* ═══════════════════════════════════════════════════════════════ */

let meetingsData = [];
let statusChartInstance = null;
let pollTimer = null;
let wsClient = null;
let activeEngineState = { is_running: false, engine: 'idle', bot_count: 0, active_count: 0 };

function requireDashboardAuth() {
    const auth = localStorage.getItem('zomo_admin_auth');
    if (!auth) {
        window.location.href = '/login';
        return false;
    }
    return true;
}

function getStoredUser() {
    const raw = localStorage.getItem('zomo_admin_auth');
    return raw ? JSON.parse(raw) : null;
}

function logoutFromDashboard() {
    localStorage.removeItem('zomo_admin_auth');
    localStorage.removeItem('authToken');
    window.location.href = '/login';
}

window.logoutFromDashboard = logoutFromDashboard;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    if (!requireDashboardAuth()) return;

    const user = getStoredUser();
    const isSuperadmin = user && (user.role === 'superadmin' || user.role === 'admin');

    const adminButton = document.querySelector('[data-action="go-admin"]');
    if (adminButton) {
        if (isSuperadmin) {
            adminButton.style.display = 'inline-flex';
            adminButton.addEventListener('click', () => {
                window.location.href = '/admin';
            });
        } else {
            // Hide User Management button from regular users
            adminButton.style.display = 'none';
        }
    }

    const logoutButton = document.querySelector('[data-action="logout-dashboard"]');
    if (logoutButton) {
        logoutButton.addEventListener('click', logoutFromDashboard);
    }

    initializeDashboard();
    setupEventListeners();
});

// Initialize dashboard components
async function initializeDashboard() {
    await fetchMeetings();
    setTimeout(() => {
        initializeStatusChart();
    }, 300);

    startBackendStatusPolling();
    connectWebSocketLogs();
}

// Setup event listeners
function setupEventListeners() {
    const botConfigForm = document.getElementById('botConfigForm');
    if (botConfigForm) {
        botConfigForm.addEventListener('submit', handleFormSubmit);
    }

    const editForm = document.getElementById('editForm');
    if (editForm) {
        editForm.addEventListener('submit', handleEditFormSubmit);
    }
}

// Fetch meetings list from backend (isolated to current user)
async function fetchMeetings() {
    try {
        const headers = typeof getAuthHeaders === 'function' ? getAuthHeaders() : {};
        const res = await fetch('/api/meetings', { headers });
        if (res.ok) {
            const data = await res.json();
            if (data && data.meetings) {
                meetingsData = data.meetings;
            }
        }
    } catch (err) {
        console.warn('Failed to fetch meetings from backend:', err);
    }
    loadMeetingsTable();
    updateChartFromMeetings();
}

// Handle form submission for launching bot
async function handleFormSubmit(e) {
    e.preventDefault();

    const meetingIdRaw = document.getElementById('meetingId').value.trim();
    const password = document.getElementById('meetingPassword') ? document.getElementById('meetingPassword').value.trim() : '';
    const botCount = parseInt(document.getElementById('botUsersCount').value, 10) || 1;
    const nameLocale = document.getElementById('nameLocale') ? document.getElementById('nameLocale').value.trim() : 'en-US';
    const timeoutMin = parseInt(document.getElementById('timeout').value, 10) || 30;
    const vcType = document.getElementById('vcType') ? document.getElementById('vcType').value : 'zoom';

    let meetingUrl = meetingIdRaw;
    if (meetingIdRaw.replace(/\s+/g, '').match(/^\d{9,11}$/)) {
        const cleanId = meetingIdRaw.replace(/\s+/g, '');
        meetingUrl = `https://zoom.us/j/${cleanId}` + (password ? `?pwd=${encodeURIComponent(password)}` : '');
    } else if (password && !meetingUrl.includes('pwd=')) {
        meetingUrl += (meetingUrl.includes('?') ? '&' : '?') + `pwd=${encodeURIComponent(password)}`;
    }

    showNotification(`🚀 Launching ${botCount} bot participant(s)...`, 'info');

    const submitBtn = e.target.querySelector('button[type="submit"]');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerText = 'LAUNCHING...';
    }

    try {
        const payload = {
            meeting_url: meetingUrl,
            meetingId: meetingIdRaw,
            bot_count: botCount,
            timeout: timeoutMin * 60,
            vcType: vcType,
            engine: 'web_farm',
            per_bot_browser: true
        };

        const headers = typeof getAuthHeaders === 'function' ? getAuthHeaders() : { 'Content-Type': 'application/json' };
        const response = await fetch('/api/bot/start', {
            method: 'POST',
            headers,
            body: JSON.stringify(payload)
        });

        const result = await response.json();
        if (response.ok && result.status === 'ok') {
            showNotification(result.message || 'Bot participant started successfully!', 'success');
        } else {
            showNotification(result.message || 'Bot launch issue.', 'warning');
        }
    } catch (err) {
        console.warn('API start call error:', err);
        showNotification('Bot launched in simulation mode.', 'info');
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerText = 'SUBMIT & LAUNCH';
        }
        e.target.reset();
        await fetchMeetings();
    }
}

// Load meetings table
function loadMeetingsTable() {
    const tbody = document.getElementById('meetingsTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (meetingsData.length === 0) {
        const emptyRow = document.createElement('tr');
        emptyRow.innerHTML = `<td colspan="7" style="text-align: center; color: var(--text-muted); padding: 24px;">No meetings recorded yet for your account. Use the form to launch a bot.</td>`;
        tbody.appendChild(emptyRow);
        return;
    }

    meetingsData.forEach((meeting, index) => {
        const row = document.createElement('tr');
        const isActive = meeting.status === 'active';
        const isQueued = meeting.status === 'queued';
        
        let statusBadge = '';
        if (isActive) {
            statusBadge = '<span class="badge badge-success" style="background: rgba(16, 185, 129, 0.2); color: #10b981; padding: 3px 8px; border-radius: 4px; font-weight: 700; font-size: 11px; display: inline-flex; align-items: center; gap: 4px;"><span style="width: 6px; height: 6px; border-radius: 50%; background: #10b981; animation: pulse 1.5s infinite;"></span> Active</span>';
        } else if (isQueued) {
            statusBadge = '<span class="badge badge-warning" style="background: rgba(245, 158, 11, 0.2); color: #f59e0b; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 11px;">Queued</span>';
        } else if (meeting.status === 'stopped') {
            statusBadge = '<span class="badge badge-danger" style="background: rgba(239, 68, 68, 0.2); color: #ef4444; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 11px;">Stopped</span>';
        } else {
            statusBadge = '<span class="badge badge-info" style="background: rgba(59, 130, 246, 0.2); color: #3b82f6; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 11px;">Completed</span>';
        }

        const actionButtons = isActive ? `
            <button class="btn btn-danger" style="padding: 5px 10px; font-size: 11px; font-weight: 700;" onclick="stopMeeting('${meeting.id}')" title="Stop Running Bots">
                ⏹ Stop
            </button>
        ` : `
            <div style="display: flex; gap: 6px;">
                <button class="btn btn-primary" style="padding: 5px 10px; font-size: 11px;" onclick="openEditModal('${meeting.id}')" title="Edit Meeting">
                    Edit
                </button>
                <button class="btn btn-danger" style="padding: 5px 8px; font-size: 11px;" onclick="deleteMeeting('${meeting.id}')" title="Delete Meeting">
                    ✕
                </button>
            </div>
        `;

        row.innerHTML = `
            <td>${index + 1}</td>
            <td><strong>${escapeHtml(meeting.meetingId)}</strong></td>
            <td><span style="font-weight: 700; color: var(--accent-primary);">${meeting.botCount}</span></td>
            <td>${escapeHtml(meeting.startTime || '—')}</td>
            <td>${meeting.timeout} min</td>
            <td>${statusBadge}</td>
            <td>
                <div style="display: flex; align-items: center; gap: 8px;">
                    ${actionButtons}
                    <button class="btn btn-ghost" style="padding: 5px 8px; font-size: 11px;" onclick="viewAnalytics('${meeting.id}')" title="View Details">
                        📊
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
}

// Stop running meeting
async function stopMeeting(meetingId) {
    showNotification('⏹ Stopping bot execution...', 'info');
    try {
        const headers = typeof getAuthHeaders === 'function' ? getAuthHeaders() : {};
        const res = await fetch(`/api/meetings/${meetingId}/stop`, { method: 'POST', headers });
        const result = await res.json();
        if (res.ok) {
            showNotification(result.message || 'Bot stopped successfully.', 'success');
        } else {
            showNotification(result.message || 'Could not stop bot.', 'warning');
        }
    } catch (err) {
        showNotification('Bot stop requested.', 'info');
    }
    await fetchMeetings();
}

// Delete meeting
async function deleteMeeting(meetingId) {
    try {
        const headers = typeof getAuthHeaders === 'function' ? getAuthHeaders() : {};
        const res = await fetch(`/api/meetings/${meetingId}`, { method: 'DELETE', headers });
        const result = await res.json();
        if (res.ok && result.status === 'ok') {
            showNotification('Meeting record deleted.', 'success');
        }
    } catch (err) {
        console.error('Delete meeting error:', err);
    }
    await fetchMeetings();
}

// Open edit modal
function openEditModal(meetingId) {
    const meeting = meetingsData.find(m => String(m.id) === String(meetingId));
    if (!meeting) return;

    document.getElementById('editMeetingId').value = meeting.meetingId;
    document.getElementById('editBotCount').value = meeting.botCount;
    document.getElementById('editTimeout').value = meeting.timeout;

    const editForm = document.getElementById('editForm');
    if (editForm) editForm.dataset.meetingId = meetingId;

    const modal = document.getElementById('editModal');
    if (modal) {
        modal.classList.add('active');
        modal.style.display = 'flex';
    }
}

// Close edit modal
function closeEditModal() {
    const modal = document.getElementById('editModal');
    if (modal) {
        modal.classList.remove('active');
        modal.style.display = 'none';
    }
}

// Handle edit form submission
async function handleEditFormSubmit(e) {
    e.preventDefault();

    const meetingId = e.target.dataset.meetingId;
    const newMeetingId = document.getElementById('editMeetingId').value.trim();
    const newBotCount = parseInt(document.getElementById('editBotCount').value, 10);
    const newTimeout = parseInt(document.getElementById('editTimeout').value, 10);

    try {
        const headers = typeof getAuthHeaders === 'function' ? getAuthHeaders() : { 'Content-Type': 'application/json' };
        const res = await fetch(`/api/meetings/${meetingId}`, {
            method: 'PUT',
            headers,
            body: JSON.stringify({
                meetingId: newMeetingId,
                botCount: newBotCount,
                timeout: newTimeout
            })
        });
        const result = await res.json();
        if (res.ok && result.status === 'ok') {
            showNotification('Meeting updated successfully!', 'success');
            closeEditModal();
            await fetchMeetings();
        } else {
            showNotification(result.message || 'Failed to update meeting.', 'error');
        }
    } catch (err) {
        console.error('Edit meeting error:', err);
        showNotification('Server communication error.', 'error');
    }
}

// Download today's details
function downloadTodayDetails() {
    if (meetingsData.length === 0) {
        showNotification('No meeting data to download.', 'warning');
        return;
    }

    const csvContent = [
        ['#', 'Meeting ID', 'Bot Users Count', 'Start Time', 'Timeout (min)', 'Status'],
        ...meetingsData.map((m, i) => [
            i + 1,
            m.meetingId,
            m.botCount,
            m.startTime || '',
            m.timeout,
            m.status
        ])
    ]
        .map(row => row.map(cell => `"${cell}"`).join(','))
        .join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `meetings_${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);

    showNotification('File downloaded successfully!', 'success');
}

// View analytics for a meeting
function viewAnalytics(meetingId) {
    const meeting = meetingsData.find(m => String(m.id) === String(meetingId));
    if (!meeting) return;

    showNotification(`Meeting ${meeting.meetingId}: ${meeting.botCount} bots | Status: ${(meeting.status || 'unknown').toUpperCase()}`, 'info');
}

// Open user settings
function openUserSettings() {
    const user = getStoredUser() || { email: 'admin@example.com', role: 'superadmin' };
    const roleLabel = (user.role === 'superadmin' || user.role === 'admin') ? 'SUPERADMIN' : 'USER';
    showNotification(`Logged in as: ${user.name || user.email} (${roleLabel})`, 'info');
}

// Notification system
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type}`;
    notification.style.position = 'fixed';
    notification.style.top = '20px';
    notification.style.right = '20px';
    notification.style.zIndex = '9999';
    notification.style.maxWidth = '400px';
    notification.style.padding = '12px 18px';
    notification.style.borderRadius = '8px';
    notification.style.boxShadow = '0 10px 25px rgba(0,0,0,0.3)';
    notification.style.display = 'flex';
    notification.style.alignItems = 'center';
    notification.style.gap = '10px';
    notification.style.fontSize = '13px';
    notification.style.fontWeight = '600';
    notification.style.color = '#fff';
    notification.style.backgroundColor = type === 'success' ? '#10b981' : type === 'danger' || type === 'error' ? '#ef4444' : type === 'warning' ? '#f59e0b' : '#3b82f6';
    notification.style.animation = 'slideIn 300ms ease-out';

    notification.innerHTML = `
        <span>${getAlertIcon(type)}</span>
        <div>${escapeHtml(message)}</div>
    `;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transition = 'opacity 300ms ease';
        setTimeout(() => notification.remove(), 300);
    }, 3500);
}

function getAlertIcon(type) {
    const icons = {
        success: '✓',
        danger: '✕',
        error: '✕',
        warning: '⚠',
        info: 'ℹ'
    };
    return icons[type] || icons.info;
}

// Initialize status chart (calculated from current user's meetings)
function initializeStatusChart() {
    const ctx = document.getElementById('statusChart');
    if (!ctx) return;

    const counts = calculateStatusCounts();

    statusChartInstance = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Active', 'Queued', 'Completed', 'Failed/Stopped'],
            datasets: [{
                data: [counts.active, counts.queued, counts.completed, counts.failed],
                backgroundColor: [
                    '#10b981', // Active - Green
                    '#f59e0b', // Queued - Amber
                    '#3b82f6', // Completed - Blue
                    '#ef4444'  // Failed - Red
                ],
                borderColor: getComputedStyle(document.documentElement).getPropertyValue('--bg-elevated').trim() || '#1a2333',
                borderWidth: 2,
                borderRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return context.label + ': ' + context.parsed + ' bots';
                        }
                    }
                }
            },
            cutout: '65%'
        }
    });
}

// Listen for theme changes to update chart border
window.addEventListener('click', (e) => {
    if (e.target.closest('#themeToggleBtn, [data-action="toggle-theme"]')) {
        setTimeout(() => {
            if (statusChartInstance) {
                const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg-elevated').trim();
                statusChartInstance.data.datasets[0].borderColor = bg;
                statusChartInstance.update();
            }
        }, 50);
    }
});

function calculateStatusCounts() {
    let active = 0, queued = 0, completed = 0, failed = 0;
    meetingsData.forEach(m => {
        const count = parseInt(m.botCount, 10) || 1;
        if (m.status === 'active') active += count;
        else if (m.status === 'queued') queued += count;
        else if (m.status === 'completed') completed += count;
        else if (m.status === 'failed' || m.status === 'stopped') failed += count;
    });

    return {
        active: active,
        queued: queued,
        completed: completed || (active === 0 && failed === 0 && meetingsData.length === 0 ? 0 : completed),
        failed: failed
    };
}

function updateChartFromMeetings() {
    if (!statusChartInstance) return;
    const counts = calculateStatusCounts();
    statusChartInstance.data.datasets[0].data = [counts.active, counts.queued, counts.completed, counts.failed];
    statusChartInstance.update();
}

function startBackendStatusPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
        try {
            const headers = typeof getAuthHeaders === 'function' ? getAuthHeaders() : {};
            const mbRes = await fetch('/api/multibot/status', { headers });
            if (mbRes.ok) {
                const mbStat = await mbRes.json();
                if (mbStat.is_running) {
                    activeEngineState = {
                        is_running: true,
                        engine: 'web_farm',
                        bot_count: mbStat.bot_count || 0,
                        active_count: mbStat.active_count || 0
                    };
                } else {
                    const botRes = await fetch('/api/bot/status', { headers });
                    if (botRes.ok) {
                        const botStat = await botRes.json();
                        const isRunning = botStat.state && !['idle', 'stopped', 'error'].includes(botStat.state);
                        activeEngineState = {
                            is_running: isRunning,
                            engine: botStat.engine || 'desktop',
                            bot_count: isRunning ? 1 : 0,
                            active_count: isRunning ? 1 : 0
                        };
                    }
                }
                updateChartFromMeetings();
            }
        } catch (e) {}
    }, 3000);
}

// Real-time WebSocket live logs connection
function connectWebSocketLogs() {
    try {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/logs`;
        wsClient = new WebSocket(wsUrl);

        wsClient.onopen = () => {
            console.log('[Zomo WS] Connected to live logs stream');
        };

        wsClient.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'log' && msg.data) {
                    if (msg.data.level === 'error') {
                        showNotification(msg.data.message, 'error');
                    }
                }
            } catch (e) {}
        };

        wsClient.onclose = () => {
            setTimeout(connectWebSocketLogs, 5000);
        };
    } catch (e) {
        console.warn('[Zomo WS] Connection error:', e);
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, function(m) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m];
    });
}

// Close modal on backdrop click
window.addEventListener('click', (event) => {
    const modal = document.getElementById('editModal');
    if (event.target === modal) {
        closeEditModal();
    }
});

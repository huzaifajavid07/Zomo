/* ═══════════════════════════════════════════════════════════════ */
/* USER MANAGEMENT ADMIN LOGIC — SUPERADMIN ONLY */
/* ═══════════════════════════════════════════════════════════════ */

let usersData = [];
let userToDelete = null;

function requireSuperAdminAuth() {
    const raw = localStorage.getItem('zomo_admin_auth');
    if (!raw) {
        window.location.href = '/login';
        return false;
    }
    try {
        const user = JSON.parse(raw);
        if (user.role !== 'superadmin' && user.role !== 'admin') {
            alert('Access Denied: Superadmin privileges required.');
            window.location.href = '/';
            return false;
        }
    } catch (e) {
        window.location.href = '/login';
        return false;
    }
    return true;
}

function initAdminPage() {
    if (!requireSuperAdminAuth()) return;
    fetchUsersFromBackend();
    setupEventListeners();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAdminPage);
} else {
    initAdminPage();
}

function setupEventListeners() {
    const userForm = document.getElementById('userForm');
    if (userForm) {
        userForm.addEventListener('submit', handleUserFormSubmit);
    }

    const searchInput = document.getElementById('searchUsers');
    if (searchInput) {
        searchInput.addEventListener('input', filterUsers);
    }

    window.addEventListener('click', (event) => {
        const userModal = document.getElementById('userModal');
        const deleteModal = document.getElementById('deleteModal');

        if (event.target === userModal) {
            closeUserModal();
        }

        if (event.target === deleteModal) {
            closeDeleteModal();
        }
    });
}

async function fetchUsersFromBackend() {
    try {
        const headers = typeof getAuthHeaders === 'function' ? getAuthHeaders() : {};
        const res = await fetch('/api/users', { headers });
        if (res.ok) {
            const data = await res.json();
            if (data && data.users) {
                usersData = data.users;
            }
        } else if (res.status === 403) {
            alert('Access Denied: Superadmin access required.');
            window.location.href = '/';
            return;
        }
    } catch (err) {
        console.warn('Could not fetch users from backend:', err);
    }
    loadUsersTable();
}

function loadUsersTable() {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;

    tbody.innerHTML = '';

    if (usersData.length === 0) {
        const emptyRow = document.createElement('tr');
        emptyRow.innerHTML = `<td colspan="7" style="text-align: center; color: var(--text-muted); padding: 24px;">No users registered yet.</td>`;
        tbody.appendChild(emptyRow);
        return;
    }

    usersData.forEach((user, index) => {
        const row = document.createElement('tr');
        const statusBadge = user.status === 'active'
            ? '<span class="badge badge-success" style="background: rgba(16, 185, 129, 0.2); color: #10b981; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 11px;">Active</span>'
            : '<span class="badge badge-danger" style="background: rgba(239, 68, 68, 0.2); color: #ef4444; padding: 3px 8px; border-radius: 4px; font-weight: 600; font-size: 11px;">Inactive</span>';

        const isSuper = user.role === 'superadmin' || user.role === 'admin';
        const roleBadge = isSuper
            ? '<span class="tag" style="background: rgba(59, 130, 246, 0.25); color: #60a5fa; font-weight: 700; padding: 2px 8px; border-radius: 4px; font-size: 11px;">Super Admin</span>'
            : '<span class="tag" style="background: var(--bg-tertiary); color: var(--text-secondary); padding: 2px 8px; border-radius: 4px; font-size: 11px;">User</span>';

        row.innerHTML = `
            <td>${index + 1}</td>
            <td><strong>${escapeHtml(user.email)}</strong></td>
            <td>${escapeHtml(user.name)}</td>
            <td>${roleBadge}</td>
            <td>${statusBadge}</td>
            <td>${formatDate(user.created)}</td>
            <td>
                <div style="display: flex; gap: 8px;">
                    <button class="btn btn-ghost" style="padding: 6px 12px; font-size: 12px;" 
                            onclick="openEditUserModal('${user.id}')">
                        Edit
                    </button>
                    <button class="btn btn-danger" style="padding: 6px 12px; font-size: 12px;" 
                            onclick="openDeleteModal('${user.id}')">
                        Delete
                    </button>
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function filterUsers(e) {
    const searchTerm = (e.target.value || '').toLowerCase();
    const rows = document.querySelectorAll('#usersTableBody tr');

    rows.forEach((row) => {
        if (row.cells.length < 3) return;
        const email = (row.cells[1]?.textContent || '').toLowerCase();
        const name = (row.cells[2]?.textContent || '').toLowerCase();
        row.style.display = (email.includes(searchTerm) || name.includes(searchTerm)) ? '' : 'none';
    });
}

function openCreateUserModal() {
    const modalTitle = document.getElementById('modalTitle');
    const form = document.getElementById('userForm');
    const modal = document.getElementById('userModal');
    const passwordGroup = document.getElementById('passwordGroup');
    const passwordInput = document.getElementById('userPassword');

    if (modalTitle) modalTitle.textContent = 'Create New User Account';
    if (form) {
        form.reset();
        form.removeAttribute('data-user-id');
    }
    if (passwordGroup) passwordGroup.style.display = 'block';
    if (passwordInput) {
        passwordInput.required = true;
        passwordInput.value = '';
    }
    if (modal) {
        modal.classList.add('active');
        modal.style.display = 'flex';
    }
}

function openEditUserModal(userId) {
    const user = usersData.find((u) => String(u.id) === String(userId));
    if (!user) return;

    const modalTitle = document.getElementById('modalTitle');
    const emailInput = document.getElementById('userEmail');
    const nameInput = document.getElementById('userName');
    const roleInput = document.getElementById('userRole');
    const passwordGroup = document.getElementById('passwordGroup');
    const passwordInput = document.getElementById('userPassword');
    const form = document.getElementById('userForm');
    const modal = document.getElementById('userModal');

    if (modalTitle) modalTitle.textContent = `Edit Account: ${user.name}`;
    if (emailInput) emailInput.value = user.email || '';
    if (nameInput) nameInput.value = user.name || '';
    if (roleInput) roleInput.value = (user.role === 'superadmin' || user.role === 'admin') ? 'superadmin' : 'user';
    if (passwordGroup) passwordGroup.style.display = 'none';
    if (passwordInput) passwordInput.required = false;
    if (form) form.dataset.userId = userId;

    if (modal) {
        modal.classList.add('active');
        modal.style.display = 'flex';
    }
}

function closeUserModal() {
    const modal = document.getElementById('userModal');
    const form = document.getElementById('userForm');

    if (modal) {
        modal.classList.remove('active');
        modal.style.display = 'none';
    }

    if (form) {
        form.removeAttribute('data-user-id');
    }
}

async function handleUserFormSubmit(e) {
    e.preventDefault();

    const userId = e.target.dataset.userId;
    const emailInput = document.getElementById('userEmail');
    const nameInput = document.getElementById('userName');
    const roleInput = document.getElementById('userRole');
    const passwordInput = document.getElementById('userPassword');

    const formData = {
        email: emailInput ? emailInput.value.trim() : '',
        name: nameInput ? nameInput.value.trim() : '',
        role: roleInput ? roleInput.value : 'user',
    };
    if (passwordInput && passwordInput.value) {
        formData.password = passwordInput.value;
    }

    if (!formData.email || !formData.name || !formData.role) {
        showNotification('Please fill in all required fields.', 'error');
        return;
    }

    if (!userId && (!passwordInput || !formData.password)) {
        showNotification('Password is required for a new user.', 'error');
        return;
    }

    try {
        const headers = typeof getAuthHeaders === 'function' ? getAuthHeaders() : { 'Content-Type': 'application/json' };
        if (userId) {
            const res = await fetch(`/api/users/${userId}`, {
                method: 'PUT',
                headers,
                body: JSON.stringify(formData)
            });
            const data = await res.json();
            if (res.ok && data.status === 'ok') {
                showNotification('User updated successfully!', 'success');
                await fetchUsersFromBackend();
                closeUserModal();
            } else {
                showNotification(data.message || 'Failed to update user.', 'error');
            }
        } else {
            const res = await fetch('/api/users', {
                method: 'POST',
                headers,
                body: JSON.stringify(formData)
            });
            const data = await res.json();
            if (res.ok && data.status === 'ok') {
                showNotification('User account created successfully!', 'success');
                await fetchUsersFromBackend();
                closeUserModal();
            } else {
                showNotification(data.message || 'Failed to create user.', 'error');
            }
        }
    } catch (err) {
        console.error('Error submitting user:', err);
        showNotification('Server communication error.', 'error');
    }
}

function openDeleteModal(userId) {
    userToDelete = userId;
    const modal = document.getElementById('deleteModal');
    if (modal) {
        modal.classList.add('active');
        modal.style.display = 'flex';
    }
}

function closeDeleteModal() {
    const modal = document.getElementById('deleteModal');
    if (modal) {
        modal.classList.remove('active');
        modal.style.display = 'none';
    }
    userToDelete = null;
}

async function confirmDelete() {
    if (!userToDelete) return;

    try {
        const headers = typeof getAuthHeaders === 'function' ? getAuthHeaders() : {};
        const res = await fetch(`/api/users/${userToDelete}`, {
            method: 'DELETE',
            headers
        });
        const data = await res.json();
        if (res.ok && data.status === 'ok') {
            showNotification('User account deleted.', 'success');
            await fetchUsersFromBackend();
            closeDeleteModal();
        } else {
            showNotification(data.message || 'Failed to delete user.', 'error');
        }
    } catch (err) {
        console.error('Error deleting user:', err);
        showNotification('Server communication error.', 'error');
    }
}

function goBack() {
    window.location.href = '/';
}

function logoutAdmin() {
    localStorage.removeItem('zomo_admin_auth');
    localStorage.removeItem('authToken');
    window.location.href = '/login';
}

function formatDate(dateString) {
    if (!dateString) return '—';

    const date = new Date(dateString);
    return isNaN(date) ? dateString : date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>"']/g, function(m) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m];
    });
}

function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type}`;
    notification.style.position = 'fixed';
    notification.style.top = '20px';
    notification.style.right = '20px';
    notification.style.zIndex = '9999';
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

    notification.textContent = message;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transition = 'opacity 300ms ease';
        setTimeout(() => notification.remove(), 300);
    }, 3500);
}

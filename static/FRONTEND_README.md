# Zomo - Modern Dashboard Frontend Architecture

A modern, responsive dark-mode SaaS dashboard for managing automated virtual meeting bots.

## 📁 Project Structure

```
static/
├── index.html              # Main dashboard page
├── admin.html              # User management page
├── login.html              # Admin login page
├── FRONTEND_README.md      # Frontend documentation
├── css/
│   ├── main.css            # Base styles and animations
│   ├── theme.css           # Dark theme variables and design tokens
│   ├── dashboard.css       # Dashboard layout, cards, and forms
│   └── components.css      # Reusable UI component styles
├── js/
│   ├── dashboard.js        # Dashboard functionality & bot launch dispatch
│   ├── admin.js            # User management logic
│   ├── analytics.js        # Analytics and charts
│   └── login.js            # Admin login authentication
├── utils/
│   └── helpers.js          # Utility functions (ApiClient, StorageManager, DateUtils, etc.)
├── components/             # Reusable component modules
├── pages/                  # Page-specific logic modules
└── assets/
    └── icons/              # SVG icons
```

## 🎨 Design System

### Color Palette

- **Primary**: `#3b82f6` (Blue)
- **Secondary**: `#8b5cf6` (Purple)
- **Success**: `#10b981` (Green)
- **Warning**: `#f59e0b` (Amber)
- **Danger**: `#ef4444` (Red)
- **Info**: `#06b6d4` (Cyan)

### Dark Theme

- **Background App**: `#0d131f` (Deep Night)
- **Background Primary**: `#111827` (Deep Navy)
- **Background Secondary**: `#1e293b` (Slate)
- **Background Tertiary**: `#2e3d54` (Lighter Slate)
- **Text Primary**: `#ffffff` (Crisp White)
- **Text Secondary**: `#cbd5e1` (Light Gray)
- **Text Muted**: `#94a3b8` (Muted Slate)

### Typography

- **Font Family**: `Inter`, system fonts (San Francisco, Segoe UI, Roboto)
- **High Contrast & Readability**: Crisp font rendering, clear sizes, strong visual hierarchy.

## 📑 Pages & Routes

1. **Dashboard** (`/` or `/dashboard`):
   - 3-column layout: All Meetings Table, Bot Configuration Form, Analytics Doughnut Chart.
2. **User Management Panel** (`/admin`):
   - User management with real-time search, create user modal, and delete confirmation.
3. **Login Page** (`/login`):
   - Authentication gateway (Demo: `admin@example.com` / `admin123`).

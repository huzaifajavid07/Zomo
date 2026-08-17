"""
Zomo Data Store
Provides lightweight file-backed persistence for users and meetings with user-level isolation.
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import uuid

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
USERS_FILE = DATA_DIR / "users.json"
MEETINGS_FILE = DATA_DIR / "meetings.json"


def _ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        initial_users = [
            {
                "id": "1",
                "email": "admin@example.com",
                "name": "Super Admin",
                "password": "admin123",
                "role": "superadmin",
                "status": "active",
                "created": "2024-01-15",
            },
            {
                "id": "2",
                "email": "john.doe@example.com",
                "name": "John Doe",
                "password": "user123",
                "role": "user",
                "status": "active",
                "created": "2024-03-10",
            }
        ]
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(initial_users, f, indent=2)

    if not MEETINGS_FILE.exists():
        initial_meetings = [
            {
                "id": "1",
                "userId": "1",
                "userEmail": "admin@example.com",
                "meetingId": "950 8442 2783",
                "botCount": 5,
                "startTime": "12:30",
                "timeout": 60,
                "vcType": "zoom",
                "status": "completed",
                "created_at": time.time() - 7200,
            },
            {
                "id": "2",
                "userId": "2",
                "userEmail": "john.doe@example.com",
                "meetingId": "876 5432 1098",
                "botCount": 3,
                "startTime": "11:15",
                "timeout": 30,
                "vcType": "zoom",
                "status": "completed",
                "created_at": time.time() - 14400,
            }
        ]
        with open(MEETINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(initial_meetings, f, indent=2)


# ── Users API ──────────────────────────────────────────────────

def get_all_users() -> List[Dict[str, Any]]:
    _ensure_data_dir()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
            safe = []
            for u in users:
                c = dict(u)
                c.pop("password", None)
                safe.append(c)
            return safe
    except Exception:
        return []


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    _ensure_data_dir()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
            for u in users:
                if str(u.get("id")) == str(user_id):
                    return {k: v for k, v in u.items() if k != "password"}
    except Exception:
        pass
    return None


def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    _ensure_data_dir()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except Exception:
        return None

    email_clean = email.strip().lower()
    for user in users:
        if user.get("email", "").strip().lower() == email_clean and user.get("password") == password:
            role = user.get("role", "user")
            # Normalize legacy admin role to superadmin
            if role == "admin":
                role = "superadmin"
            safe_user = {k: v for k, v in user.items() if k != "password"}
            safe_user["role"] = role
            return safe_user
    return None


def create_user(user_data: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_data_dir()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except Exception:
        users = []

    email = user_data.get("email", "").strip().lower()
    if any(u.get("email", "").strip().lower() == email for u in users):
        raise ValueError("User with this email already exists.")

    new_id = str(uuid.uuid4())[:8]
    role = user_data.get("role", "user").lower()
    if role not in ("superadmin", "user"):
        role = "user"

    new_user = {
        "id": new_id,
        "email": user_data.get("email", "").strip(),
        "name": user_data.get("name", "").strip(),
        "password": user_data.get("password", "password123"),
        "role": role,
        "status": user_data.get("status", "active"),
        "created": time.strftime("%Y-%m-%d"),
    }
    users.append(new_user)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)
    return {k: v for k, v in new_user.items() if k != "password"}


def update_user(user_id: str, user_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    _ensure_data_dir()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except Exception:
        return None

    for i, user in enumerate(users):
        if str(user.get("id")) == str(user_id):
            if "email" in user_data and user_data["email"]:
                user["email"] = user_data["email"].strip()
            if "name" in user_data and user_data["name"]:
                user["name"] = user_data["name"].strip()
            if "role" in user_data and user_data["role"]:
                r = user_data["role"].lower()
                user["role"] = "superadmin" if r in ("superadmin", "admin") else "user"
            if "status" in user_data and user_data["status"]:
                user["status"] = user_data["status"]
            if user_data.get("password"):
                user["password"] = user_data["password"]
            users[i] = user
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(users, f, indent=2)
            return {k: v for k, v in user.items() if k != "password"}
    return None


def delete_user(user_id: str) -> bool:
    _ensure_data_dir()
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except Exception:
        return False

    new_users = [u for u in users if str(u.get("id")) != str(user_id)]
    if len(new_users) == len(users):
        return False
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(new_users, f, indent=2)
    return True


# ── Meetings API with User-Isolation ──────────────────────────

def get_all_meetings(user_id: Optional[str] = None, is_superadmin: bool = False) -> List[Dict[str, Any]]:
    _ensure_data_dir()
    try:
        with open(MEETINGS_FILE, "r", encoding="utf-8") as f:
            meetings = json.load(f)
    except Exception:
        return []

    if is_superadmin or user_id is None:
        return meetings

    # Filter meetings strictly to the calling user
    user_str = str(user_id)
    return [
        m for m in meetings
        if str(m.get("userId", "")) == user_str or str(m.get("user_id", "")) == user_str
    ]


def save_meeting(meeting: Dict[str, Any], user_id: Optional[str] = None, user_email: Optional[str] = None) -> Dict[str, Any]:
    _ensure_data_dir()
    meetings = get_all_meetings(is_superadmin=True)

    m_id = str(meeting.get("id") or str(uuid.uuid4())[:8])
    meeting["id"] = m_id
    if user_id:
        meeting["userId"] = str(user_id)
    if user_email:
        meeting["userEmail"] = str(user_email)
    if "created_at" not in meeting:
        meeting["created_at"] = time.time()
    if "startTime" not in meeting:
        meeting["startTime"] = time.strftime("%H:%M")

    existing_idx = next((i for i, m in enumerate(meetings) if str(m.get("id")) == m_id), None)
    if existing_idx is not None:
        meetings[existing_idx].update(meeting)
        result = meetings[existing_idx]
    else:
        meetings.insert(0, meeting)
        result = meeting

    with open(MEETINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(meetings, f, indent=2)
    return result


def update_meeting(meeting_id: str, updates: Dict[str, Any], user_id: Optional[str] = None, is_superadmin: bool = False) -> Optional[Dict[str, Any]]:
    _ensure_data_dir()
    meetings = get_all_meetings(is_superadmin=True)
    for i, m in enumerate(meetings):
        if str(m.get("id")) == str(meeting_id):
            if not is_superadmin and user_id and str(m.get("userId", "")) != str(user_id):
                return None  # Unauthorized
            meetings[i].update(updates)
            with open(MEETINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(meetings, f, indent=2)
            return meetings[i]
    return None


def delete_meeting(meeting_id: str, user_id: Optional[str] = None, is_superadmin: bool = False) -> bool:
    _ensure_data_dir()
    meetings = get_all_meetings(is_superadmin=True)
    m = next((m for m in meetings if str(m.get("id")) == str(meeting_id)), None)
    if not m:
        return False
    if not is_superadmin and user_id and str(m.get("userId", "")) != str(user_id):
        return False  # Unauthorized

    new_meetings = [x for x in meetings if str(x.get("id")) != str(meeting_id)]
    with open(MEETINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(new_meetings, f, indent=2)
    return True


def mark_active_meetings_as(status: str = "completed", user_id: Optional[str] = None):
    _ensure_data_dir()
    meetings = get_all_meetings(is_superadmin=True)
    changed = False
    for m in meetings:
        if m.get("status") == "active":
            if user_id is None or str(m.get("userId", "")) == str(user_id):
                m["status"] = status
                changed = True
    if changed:
        with open(MEETINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(meetings, f, indent=2)

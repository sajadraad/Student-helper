"""
Database management for RezeCoach Telegram bot
Handles all SQLite operations with proper error handling
"""

import sqlite3
import json
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, date
import os

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path: str = "rezecoach.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database with schema"""
        try:
            with open('schema.sql', 'r', encoding='utf-8') as f:
                schema = f.read()
            
            with sqlite3.connect(self.db_path) as conn:
                conn.executescript(schema)
                conn.commit()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def get_connection(self):
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    # User management
    def create_user(self, telegram_id: str, name: str = None) -> int:
        """Create new user and return user_id"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO users (telegram_id, name) VALUES (?, ?)",
                (telegram_id, name)
            )
            user_id = cursor.lastrowid
            
            # Create default preferences
            conn.execute(
                "INSERT INTO user_preferences (user_id) VALUES (?)",
                (user_id,)
            )
            conn.commit()
            return user_id
    
    def get_user(self, telegram_id: str) -> Optional[sqlite3.Row]:
        """Get user by telegram_id"""
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE telegram_id = ?",
                (telegram_id,)
            ).fetchone()
    
    def update_user(self, telegram_id: str, **kwargs) -> bool:
        """Update user fields"""
        if not kwargs:
            return False
        
        fields = []
        values = []
        for key, value in kwargs.items():
            if key in ['name', 'timezone', 'preferred_tone', 'study_stage', 
                      'faculty', 'major', 'academic_year', 'daily_reminder_time', 'allow_proactive']:
                fields.append(f"{key} = ?")
                values.append(value)
        
        if not fields:
            return False
        
        values.append(telegram_id)
        query = f"UPDATE users SET {', '.join(fields)} WHERE telegram_id = ?"
        
        with self.get_connection() as conn:
            conn.execute(query, values)
            conn.commit()
            return conn.total_changes > 0
    
    def get_user_preferences(self, user_id: int) -> Optional[sqlite3.Row]:
        """Get user preferences"""
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM user_preferences WHERE user_id = ?",
                (user_id,)
            ).fetchone()
    
    def update_user_preferences(self, user_id: int, **kwargs) -> bool:
        """Update user preferences"""
        if not kwargs:
            return False
        
        fields = []
        values = []
        for key, value in kwargs.items():
            if key in ['reminder_window_start', 'reminder_window_end', 
                      'max_proactive_messages_per_day', 'night_mode_start', 'night_mode_end']:
                fields.append(f"{key} = ?")
                values.append(value)
        
        if not fields:
            return False
        
        values.append(user_id)
        query = f"UPDATE user_preferences SET {', '.join(fields)} WHERE user_id = ?"
        
        with self.get_connection() as conn:
            conn.execute(query, values)
            conn.commit()
            return conn.total_changes > 0
    
    # Subject management
    def add_subject(self, user_id: int, name: str, priority: int = 3, note: str = None) -> int:
        """Add new subject for user"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO subjects (user_id, name, priority, note) VALUES (?, ?, ?, ?)",
                (user_id, name, priority, note)
            )
            conn.commit()
            return cursor.lastrowid
    
    def get_user_subjects(self, user_id: int) -> List[sqlite3.Row]:
        """Get all subjects for user"""
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM subjects WHERE user_id = ? ORDER BY priority DESC, created_at",
                (user_id,)
            ).fetchall()
    
    def get_subject(self, user_id: int, subject_name: str) -> Optional[sqlite3.Row]:
        """Get specific subject by name"""
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM subjects WHERE user_id = ? AND name = ?",
                (user_id, subject_name)
            ).fetchone()
    
    def update_subject_progress(self, user_id: int, subject_name: str, current_section: str) -> bool:
        """Update subject current section"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE subjects SET current_section = ?, last_activity_ts = CURRENT_TIMESTAMP WHERE user_id = ? AND name = ?",
                (current_section, user_id, subject_name)
            )
            conn.commit()
            return conn.total_changes > 0
    
    def update_subject_status(self, user_id: int, subject_name: str, status: str) -> bool:
        """Update subject status"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE subjects SET status = ?, last_activity_ts = CURRENT_TIMESTAMP WHERE user_id = ? AND name = ?",
                (status, user_id, subject_name)
            )
            conn.commit()
            return conn.total_changes > 0
    
    # Study sessions
    def start_study_session(self, user_id: int, subject_id: int = None) -> int:
        """Start new study session"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO study_sessions (user_id, subject_id, start_ts) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (user_id, subject_id)
            )
            conn.commit()
            return cursor.lastrowid
    
    def end_study_session(self, session_id: int, summary: str = None, score: int = None) -> bool:
        """End study session with summary and score"""
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE study_sessions SET end_ts = CURRENT_TIMESTAMP, summary = ?, score = ? WHERE id = ?",
                (summary, score, session_id)
            )
            conn.commit()
            return conn.total_changes > 0
    
    def get_active_session(self, user_id: int) -> Optional[sqlite3.Row]:
        """Get active study session for user"""
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM study_sessions WHERE user_id = ? AND end_ts IS NULL ORDER BY start_ts DESC LIMIT 1",
                (user_id,)
            ).fetchone()
    
    def get_recent_sessions(self, user_id: int, days: int = 7) -> List[sqlite3.Row]:
        """Get recent study sessions"""
        with self.get_connection() as conn:
            return conn.execute(
                """SELECT s.*, sub.name as subject_name 
                   FROM study_sessions s 
                   LEFT JOIN subjects sub ON s.subject_id = sub.id 
                   WHERE s.user_id = ? AND s.start_ts >= date('now', '-{} days') 
                   ORDER BY s.start_ts DESC""".format(days),
                (user_id,)
            ).fetchall()
    
    # Water logging
    def log_water(self, user_id: int, cups: int = 1) -> bool:
        """Log water intake for today"""
        today = date.today().isoformat()
        with self.get_connection() as conn:
            # Check if entry exists for today
            existing = conn.execute(
                "SELECT cups FROM water_logs WHERE user_id = ? AND date = ?",
                (user_id, today)
            ).fetchone()
            
            if existing:
                conn.execute(
                    "UPDATE water_logs SET cups = cups + ? WHERE user_id = ? AND date = ?",
                    (cups, user_id, today)
                )
            else:
                conn.execute(
                    "INSERT INTO water_logs (user_id, date, cups) VALUES (?, ?, ?)",
                    (user_id, today, cups)
                )
            conn.commit()
            return True
    
    def get_today_water(self, user_id: int) -> int:
        """Get today's water intake"""
        today = date.today().isoformat()
        with self.get_connection() as conn:
            result = conn.execute(
                "SELECT cups FROM water_logs WHERE user_id = ? AND date = ?",
                (user_id, today)
            ).fetchone()
            return result['cups'] if result else 0
    
    # Activity tracking
    def log_activity(self, user_id: int, activity_type: str, activity_data: Dict = None):
        """Log user activity for adaptive behavior"""
        data_json = json.dumps(activity_data) if activity_data else None
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO user_activity (user_id, activity_type, activity_data) VALUES (?, ?, ?)",
                (user_id, activity_type, data_json)
            )
            conn.commit()
    
    def get_recent_activity(self, user_id: int, hours: int = 24) -> List[sqlite3.Row]:
        """Get recent user activity"""
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM user_activity WHERE user_id = ? AND timestamp >= datetime('now', '-{} hours') ORDER BY timestamp DESC".format(hours),
                (user_id,)
            ).fetchall()
    
    # Proactive message tracking
    def can_send_proactive_message(self, user_id: int) -> bool:
        """Check if can send proactive message based on limits"""
        prefs = self.get_user_preferences(user_id)
        if not prefs:
            return False
        
        max_messages = prefs['max_proactive_messages_per_day']
        
        with self.get_connection() as conn:
            count = conn.execute(
                "SELECT COUNT(*) as count FROM proactive_messages WHERE user_id = ? AND sent_at >= date('now')",
                (user_id,)
            ).fetchone()
            
            return count['count'] < max_messages
    
    def log_proactive_message(self, user_id: int, message_type: str):
        """Log sent proactive message"""
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO proactive_messages (user_id, message_type) VALUES (?, ?)",
                (user_id, message_type)
            )
            conn.commit()
    
    # Weekly schedule
    def set_weekly_schedule(self, user_id: int, day_of_week: int, events: List[Dict]) -> bool:
        """Set weekly schedule for specific day"""
        events_json = json.dumps(events, ensure_ascii=False)
        with self.get_connection() as conn:
            # Delete existing schedule for this day
            conn.execute(
                "DELETE FROM weekly_schedule WHERE user_id = ? AND day_of_week = ?",
                (user_id, day_of_week)
            )
            
            # Insert new schedule
            conn.execute(
                "INSERT INTO weekly_schedule (user_id, day_of_week, events_json) VALUES (?, ?, ?)",
                (user_id, day_of_week, events_json)
            )
            conn.commit()
            return True
    
    def get_daily_schedule(self, user_id: int, day_of_week: int) -> List[Dict]:
        """Get schedule for specific day"""
        with self.get_connection() as conn:
            result = conn.execute(
                "SELECT events_json FROM weekly_schedule WHERE user_id = ? AND day_of_week = ?",
                (user_id, day_of_week)
            ).fetchone()
            
            if result and result['events_json']:
                return json.loads(result['events_json'])
            return []
    
    # File management
    def save_file(self, user_id: int, tg_file_id: str, local_path: str = None, 
                  file_type: str = None, extracted_text: str = None) -> int:
        """Save file information"""
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO files (user_id, tg_file_id, local_path, file_type, extracted_text) VALUES (?, ?, ?, ?, ?)",
                (user_id, tg_file_id, local_path, file_type, extracted_text)
            )
            conn.commit()
            return cursor.lastrowid
    
    def get_user_files(self, user_id: int, limit: int = 10) -> List[sqlite3.Row]:
        """Get recent user files"""
        with self.get_connection() as conn:
            return conn.execute(
                "SELECT * FROM files WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
    
    # Analytics and stats
    def get_user_stats(self, user_id: int, days: int = 30) -> Dict:
        """Get comprehensive user statistics"""
        with self.get_connection() as conn:
            # Study sessions stats
            session_stats = conn.execute(
                """SELECT COUNT(*) as total_sessions,
                          AVG(CAST(julianday(end_ts) - julianday(start_ts) AS REAL) * 24 * 60) as avg_duration_minutes,
                          AVG(score) as avg_score
                   FROM study_sessions 
                   WHERE user_id = ? AND start_ts >= date('now', '-{} days') AND end_ts IS NOT NULL""".format(days),
                (user_id,)
            ).fetchone()
            
            # Water intake stats
            water_stats = conn.execute(
                "SELECT AVG(cups) as avg_cups, SUM(cups) as total_cups FROM water_logs WHERE user_id = ? AND date >= date('now', '-{} days')".format(days),
                (user_id,)
            ).fetchall()
            
            # Subject activity
            subject_activity = conn.execute(
                "SELECT name, MAX(last_activity_ts) as last_activity FROM subjects WHERE user_id = ? GROUP BY name ORDER BY last_activity DESC",
                (user_id,)
            ).fetchall()
            
            return {
                'study_sessions': dict(session_stats) if session_stats else {},
                'water_intake': dict(water_stats[0]) if water_stats else {},
                'subjects': [dict(row) for row in subject_activity]
            }
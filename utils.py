"""
Utility functions for RezeCoach Telegram bot
Timezone handling, formatting, validation, and helper functions
"""

import pytz
import logging
from datetime import datetime, timedelta, time
from typing import Optional, List, Dict, Tuple, Any
import re
import json
import os
from functools import wraps
import time as time_module

logger = logging.getLogger(__name__)

# Default timezone
DEFAULT_TIMEZONE = 'Asia/Baghdad'

# Iraqi Arabic time expressions mapping
TIME_EXPRESSIONS = {
    'الصباح': '09:00',
    'الظهر': '12:00', 
    'العصر': '15:00',
    'المساء': '18:00',
    'الليل': '21:00',
    'صباح': '09:00',
    'ظهر': '12:00',
    'عصر': '15:00',
    'مساء': '18:00',
    'ليل': '21:00'
}

class TimezoneManager:
    """Handle timezone operations for users"""
    
    @staticmethod
    def get_user_timezone(timezone_str: str = None) -> pytz.BaseTzInfo:
        """Get user timezone object"""
        try:
            tz_name = timezone_str or DEFAULT_TIMEZONE
            return pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError:
            logger.warning(f"Unknown timezone: {timezone_str}, using default")
            return pytz.timezone(DEFAULT_TIMEZONE)
    
    @staticmethod
    def now_in_timezone(timezone_str: str = None) -> datetime:
        """Get current time in user's timezone"""
        tz = TimezoneManager.get_user_timezone(timezone_str)
        return datetime.now(tz)
    
    @staticmethod
    def is_night_mode(timezone_str: str = None, night_start: str = "22:30", night_end: str = "06:00") -> bool:
        """Check if current time is in night mode"""
        current_time = TimezoneManager.now_in_timezone(timezone_str).time()
        
        try:
            start_time = datetime.strptime(night_start, "%H:%M").time()
            end_time = datetime.strptime(night_end, "%H:%M").time()
            
            if start_time <= end_time:
                # Same day (e.g., 22:30 - 23:59)
                return start_time <= current_time <= end_time
            else:
                # Crosses midnight (e.g., 22:30 - 06:00)
                return current_time >= start_time or current_time <= end_time
        except ValueError:
            return False
    
    @staticmethod
    def is_in_reminder_window(timezone_str: str = None, window_start: str = "08:00", window_end: str = "22:00") -> bool:
        """Check if current time is in reminder window"""
        current_time = TimezoneManager.now_in_timezone(timezone_str).time()
        
        try:
            start_time = datetime.strptime(window_start, "%H:%M").time()
            end_time = datetime.strptime(window_end, "%H:%M").time()
            
            return start_time <= current_time <= end_time
        except ValueError:
            return True  # Default to allowing reminders
    
    @staticmethod
    def parse_time_expression(time_expr: str) -> Optional[str]:
        """Parse Arabic time expressions to HH:MM format"""
        time_expr = time_expr.strip()
        
        # Check if already in HH:MM format
        if re.match(r'^\d{1,2}:\d{2}$', time_expr):
            return time_expr
        
        # Check Arabic expressions
        for arabic, time_str in TIME_EXPRESSIONS.items():
            if arabic in time_expr:
                return time_str
        
        # Try to extract numbers
        numbers = re.findall(r'\d+', time_expr)
        if len(numbers) >= 1:
            hour = int(numbers[0])
            minute = int(numbers[1]) if len(numbers) > 1 else 0
            
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                return f"{hour:02d}:{minute:02d}"
        
        return None

class MessageFormatter:
    """Format messages for Telegram"""
    
    @staticmethod
    def format_study_session(session: Dict) -> str:
        """Format study session for display"""
        start_time = session.get('start_ts', '')
        end_time = session.get('end_ts', '')
        subject = session.get('subject_name', 'عام')
        duration = session.get('duration_minutes', 0)
        score = session.get('score', 0)
        
        duration_str = MessageFormatter.format_duration(duration)
        score_emoji = "⭐" * min(int(score or 0), 5)
        
        return f"📚 {subject}\n⏱ {duration_str}\n{score_emoji} ({score}/10)"
    
    @staticmethod
    def format_duration(minutes: float) -> str:
        """Format duration in Arabic"""
        if not minutes:
            return "غير محدد"
        
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        
        if hours > 0:
            return f"{hours} ساعة و {mins} دقيقة"
        else:
            return f"{mins} دقيقة"
    
    @staticmethod
    def format_water_intake(cups: int) -> str:
        """Format water intake message"""
        if cups == 0:
            return "ما شربت مي اليوم! 💧"
        elif cups < 4:
            return f"شربت {cups} كاسات مي 💧 (يحتاج أكثر)"
        elif cups < 8:
            return f"شربت {cups} كاسات مي 💧 (زين!)"
        else:
            return f"شربت {cups} كاسات مي 💧 (ممتاز!)"
    
    @staticmethod
    def format_subjects_list(subjects: List[Dict]) -> str:
        """Format subjects list"""
        if not subjects:
            return "ما عندك مواد مضافة بعد"
        
        text = "المواد المسجلة:\n"
        for i, subject in enumerate(subjects, 1):
            status_emoji = {
                'not_started': '⚪',
                'in_progress': '🔵', 
                'completed': '✅',
                'on_hold': '⏸'
            }.get(subject.get('status', 'not_started'), '⚪')
            
            priority_stars = "⭐" * subject.get('priority', 3)
            text += f"{i}. {status_emoji} {subject['name']} {priority_stars}\n"
        
        return text
    
    @staticmethod
    def format_weekly_schedule(schedule: List[Dict]) -> str:
        """Format weekly schedule"""
        if not schedule:
            return "ما عندك جدول لهذا اليوم"
        
        text = "جدول اليوم:\n"
        for event in schedule:
            time_str = event.get('time', '')
            title = event.get('title', '')
            text += f"⏰ {time_str} - {title}\n"
        
        return text

class RateLimiter:
    """Rate limiting for API calls and messages"""
    
    def __init__(self):
        self.calls = {}
    
    def is_allowed(self, key: str, max_calls: int, time_window: int = 3600) -> bool:
        """Check if action is allowed within time window"""
        current_time = time_module.time()
        
        if key not in self.calls:
            self.calls[key] = []
        
        # Remove old calls outside time window
        self.calls[key] = [call_time for call_time in self.calls[key] 
                          if current_time - call_time < time_window]
        
        # Check if under limit
        if len(self.calls[key]) < max_calls:
            self.calls[key].append(current_time)
            return True
        
        return False
    
    def get_reset_time(self, key: str, time_window: int = 3600) -> Optional[datetime]:
        """Get when rate limit resets"""
        if key not in self.calls or not self.calls[key]:
            return None
        
        oldest_call = min(self.calls[key])
        reset_time = datetime.fromtimestamp(oldest_call + time_window)
        return reset_time

def rate_limit(max_calls: int = 5, time_window: int = 3600):
    """Decorator for rate limiting functions"""
    limiter = RateLimiter()
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            key = f"{func.__name__}_{args[0] if args else 'global'}"
            
            if limiter.is_allowed(key, max_calls, time_window):
                return func(*args, **kwargs)
            else:
                reset_time = limiter.get_reset_time(key, time_window)
                logger.warning(f"Rate limit exceeded for {func.__name__}. Reset at {reset_time}")
                return None
        return wrapper
    return decorator

class InputValidator:
    """Validate user inputs"""
    
    @staticmethod
    def validate_time(time_str: str) -> bool:
        """Validate time format HH:MM"""
        try:
            datetime.strptime(time_str, "%H:%M")
            return True
        except ValueError:
            return False
    
    @staticmethod
    def validate_priority(priority: str) -> Optional[int]:
        """Validate priority (1-5)"""
        try:
            p = int(priority)
            return p if 1 <= p <= 5 else None
        except ValueError:
            return None
    
    @staticmethod
    def validate_score(score: str) -> Optional[int]:
        """Validate score (1-10)"""
        try:
            s = int(score)
            return s if 1 <= s <= 10 else None
        except ValueError:
            return None
    
    @staticmethod
    def sanitize_text(text: str, max_length: int = 1000) -> str:
        """Sanitize text input"""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Truncate if too long
        if len(text) > max_length:
            text = text[:max_length-3] + "..."
        
        return text
    
    @staticmethod
    def parse_command_args(text: str) -> List[str]:
        """Parse command arguments from text"""
        # Handle quoted arguments
        parts = re.findall(r'"([^"]*)"|\S+', text)
        return [part for part in parts if part]

class DataExporter:
    """Export user data for backup/analysis"""
    
    @staticmethod
    def export_user_data(db_manager, user_id: int) -> Dict:
        """Export complete user data"""
        try:
            with db_manager.get_connection() as conn:
                # User info
                user = conn.execute(
                    "SELECT * FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                
                if not user:
                    return {}
                
                # Subjects
                subjects = conn.execute(
                    "SELECT * FROM subjects WHERE user_id = ?", (user_id,)
                ).fetchall()
                
                # Study sessions
                sessions = conn.execute(
                    "SELECT * FROM study_sessions WHERE user_id = ?", (user_id,)
                ).fetchall()
                
                # Water logs
                water_logs = conn.execute(
                    "SELECT * FROM water_logs WHERE user_id = ?", (user_id,)
                ).fetchall()
                
                # Weekly schedule
                schedule = conn.execute(
                    "SELECT * FROM weekly_schedule WHERE user_id = ?", (user_id,)
                ).fetchall()
                
                return {
                    'user': dict(user),
                    'subjects': [dict(s) for s in subjects],
                    'study_sessions': [dict(s) for s in sessions],
                    'water_logs': [dict(w) for w in water_logs],
                    'weekly_schedule': [dict(sch) for sch in schedule],
                    'exported_at': datetime.now().isoformat()
                }
        except Exception as e:
            logger.error(f"Error exporting user data: {e}")
            return {}

class FileHandler:
    """Handle file operations"""
    
    @staticmethod
    def ensure_directory(path: str):
        """Ensure directory exists"""
        os.makedirs(path, exist_ok=True)
    
    @staticmethod
    def save_uploaded_file(file_content: bytes, filename: str, user_id: int) -> Optional[str]:
        """Save uploaded file and return path"""
        try:
            upload_dir = f"uploads/user_{user_id}"
            FileHandler.ensure_directory(upload_dir)
            
            # Generate unique filename
            timestamp = int(time_module.time())
            safe_filename = re.sub(r'[^\w\-_\.]', '_', filename)
            filepath = os.path.join(upload_dir, f"{timestamp}_{safe_filename}")
            
            with open(filepath, 'wb') as f:
                f.write(file_content)
            
            return filepath
        except Exception as e:
            logger.error(f"Error saving file: {e}")
            return None
    
    @staticmethod
    def extract_text_from_file(filepath: str) -> Optional[str]:
        """Extract text from various file formats"""
        try:
            file_ext = os.path.splitext(filepath)[1].lower()
            
            if file_ext == '.txt':
                with open(filepath, 'r', encoding='utf-8') as f:
                    return f.read()
            elif file_ext == '.pdf':
                # TODO: Implement PDF text extraction
                # Could use PyPDF2 or pdfplumber
                return "PDF text extraction not implemented yet"
            elif file_ext in ['.doc', '.docx']:
                # TODO: Implement Word document text extraction
                # Could use python-docx
                return "Word document text extraction not implemented yet"
            else:
                return None
        except Exception as e:
            logger.error(f"Error extracting text from {filepath}: {e}")
            return None

# Arabic text utilities
def contains_arabic(text: str) -> bool:
    """Check if text contains Arabic characters"""
    arabic_pattern = re.compile(r'[\u0600-\u06FF]')
    return bool(arabic_pattern.search(text))

def clean_arabic_text(text: str) -> str:
    """Clean Arabic text for processing"""
    # Remove diacritics
    text = re.sub(r'[\u064B-\u0652]', '', text)
    # Normalize spaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# Configuration helpers
def get_env_var(name: str, default: Any = None, required: bool = False) -> Any:
    """Get environment variable with validation"""
    value = os.environ.get(name, default)
    
    if required and value is None:
        raise ValueError(f"Required environment variable {name} is not set")
    
    return value

def setup_logging(level: str = "INFO") -> None:
    """Setup logging configuration"""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('rezecoach.log'),
            logging.StreamHandler()
        ]
    )
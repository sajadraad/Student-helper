"""
Scheduled and event-driven jobs for RezeCoach
Handles proactive messaging, reminders, and adaptive interventions
"""

import asyncio
import schedule
import time
import logging
from datetime import datetime, timedelta, time as datetime_time
from typing import Dict, List, Optional
import threading
from telegram import Bot
from telegram.error import TelegramError

from db import DatabaseManager
from ai import GeminiAI
from utils import TimezoneManager, MessageFormatter, rate_limit

logger = logging.getLogger(__name__)

class JobScheduler:
    def __init__(self, bot: Bot, db_manager: DatabaseManager, ai: GeminiAI):
        self.bot = bot
        self.db = db_manager
        self.ai = ai
        self.running = False
        self.scheduler_thread = None
        
        # Rate limiting for proactive messages
        self.message_counts = {}
        
    def start(self):
        """Start the job scheduler"""
        if self.running:
            return
        
        self.running = True
        
        # Schedule recurring jobs
        self._schedule_jobs()
        
        # Start scheduler in separate thread
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        logger.info("Job scheduler started")
    
    def stop(self):
        """Stop the job scheduler"""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join()
        logger.info("Job scheduler stopped")
    
    def _schedule_jobs(self):
        """Schedule all recurring jobs"""
        
        # Morning check-ins (run every 30 minutes during morning hours)
        schedule.every(30).minutes.do(self._check_morning_reminders)
        
        # Class end check-ins (run every hour)
        schedule.every().hour.do(self._check_class_end_reminders)
        
        # Hydration reminders (run every 2 hours during day)
        schedule.every(2).hours.do(self._check_hydration_reminders)
        
        # Evening recaps (run every 30 minutes during evening)
        schedule.every(30).minutes.do(self._check_evening_recaps)
        
        # Weekly evaluations (run daily to check if it's time)
        schedule.every().day.at("20:00").do(self._check_weekly_evaluations)
        
        # Adaptive interventions (run every hour)
        schedule.every().hour.do(self._run_adaptive_interventions)
        
        # Cleanup old data (run daily)
        schedule.every().day.at("02:00").do(self._cleanup_old_data)
        
        logger.info("Jobs scheduled successfully")
    
    def _run_scheduler(self):
        """Run the scheduler loop"""
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                time.sleep(300)  # Wait 5 minutes on error
    
    @rate_limit(max_calls=50, time_window=3600)  # Max 50 messages per hour
    async def _send_proactive_message(self, telegram_id: str, message: str, message_type: str = "general") -> bool:
        """Send proactive message with rate limiting and tracking"""
        try:
            # Check if user allows proactive messages
            user = self.db.get_user(telegram_id)
            if not user or not user['allow_proactive']:
                return False
            
            # Check daily limits
            if not self.db.can_send_proactive_message(user['id']):
                logger.info(f"Daily limit reached for user {telegram_id}")
                return False
            
            # Check night mode
            if TimezoneManager.is_night_mode(
                user['timezone'], 
                user.get('night_mode_start', '22:30'),
                user.get('night_mode_end', '06:00')
            ):
                logger.info(f"Night mode active for user {telegram_id}")
                return False
            
            # Check reminder window
            prefs = self.db.get_user_preferences(user['id'])
            if prefs and not TimezoneManager.is_in_reminder_window(
                user['timezone'],
                prefs['reminder_window_start'],
                prefs['reminder_window_end']
            ):
                return False
            
            # Send message
            await self.bot.send_message(chat_id=telegram_id, text=message)
            
            # Log the proactive message
            self.db.log_proactive_message(user['id'], message_type)
            
            logger.info(f"Proactive message sent to {telegram_id}: {message_type}")
            return True
            
        except TelegramError as e:
            if e.message == "Forbidden: bot was blocked by the user":
                logger.info(f"Bot blocked by user {telegram_id}")
                # Could mark user as inactive here
            else:
                logger.error(f"Telegram error sending to {telegram_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending proactive message: {e}")
            return False
    
    def _check_morning_reminders(self):
        """Check and send morning reminders"""
        current_hour = datetime.now().hour
        
        # Only run during morning hours
        if not (6 <= current_hour <= 11):
            return
        
        try:
            # Get users who need morning reminders
            with self.db.get_connection() as conn:
                users = conn.execute(
                    """SELECT u.*, p.reminder_window_start 
                       FROM users u 
                       LEFT JOIN user_preferences p ON u.id = p.user_id
                       WHERE u.allow_proactive = 1"""
                ).fetchall()
            
            for user in users:
                asyncio.create_task(self._process_morning_reminder(user))
                
        except Exception as e:
            logger.error(f"Error checking morning reminders: {e}")
    
    async def _process_morning_reminder(self, user):
        """Process morning reminder for specific user"""
        try:
            # Check if reminder time matches
            user_tz = TimezoneManager.get_user_timezone(user['timezone'])
            current_time = datetime.now(user_tz)
            
            reminder_time = datetime.strptime(user['daily_reminder_time'], "%H:%M").time()
            
            # Check if within 30 minutes of reminder time
            time_diff = abs(
                (current_time.time().hour * 60 + current_time.time().minute) -
                (reminder_time.hour * 60 + reminder_time.minute)
            )
            
            if time_diff > 30:  # More than 30 minutes difference
                return
            
            # Check if already sent today
            today = current_time.date()
            with self.db.get_connection() as conn:
                sent_today = conn.execute(
                    """SELECT COUNT(*) as count FROM proactive_messages 
                       WHERE user_id = ? AND message_type = 'morning_reminder' 
                       AND DATE(sent_at) = ?""",
                    (user['id'], today.isoformat())
                ).fetchone()
                
                if sent_today['count'] > 0:
                    return
            
            # Get daily events
            today_weekday = current_time.weekday()
            daily_events = self.db.get_daily_schedule(user['id'], today_weekday)
            event_list = [event.get('title', '') for event in daily_events[:3]]
            
            # Generate morning message
            morning_message = self.ai.generate_morning_greeting(user['name'], event_list)
            
            # Add today's schedule if available
            if daily_events:
                schedule_text = MessageFormatter.format_weekly_schedule(daily_events)
                morning_message += f"\n\n{schedule_text}"
            
            await self._send_proactive_message(
                user['telegram_id'], 
                morning_message, 
                'morning_reminder'
            )
            
        except Exception as e:
            logger.error(f"Error processing morning reminder for user {user['telegram_id']}: {e}")
    
    def _check_class_end_reminders(self):
        """Check for class end reminders"""
        try:
            current_time = datetime.now()
            
            # Get users with schedules
            with self.db.get_connection() as conn:
                users = conn.execute(
                    """SELECT DISTINCT u.* FROM users u 
                       JOIN weekly_schedule ws ON u.id = ws.user_id 
                       WHERE u.allow_proactive = 1"""
                ).fetchall()
            
            for user in users:
                asyncio.create_task(self._check_user_class_ends(user, current_time))
                
        except Exception as e:
            logger.error(f"Error checking class end reminders: {e}")
    
    async def _check_user_class_ends(self, user, current_time):
        """Check class ends for specific user"""
        try:
            user_tz = TimezoneManager.get_user_timezone(user['timezone'])
            user_current_time = current_time.astimezone(user_tz)
            
            # Get today's schedule
            today_schedule = self.db.get_daily_schedule(user['id'], user_current_time.weekday())
            
            for event in today_schedule:
                event_time_str = event.get('end_time') or event.get('time', '')
                if not event_time_str:
                    continue
                
                try:
                    event_time = datetime.strptime(event_time_str, "%H:%M").time()
                    event_datetime = datetime.combine(user_current_time.date(), event_time)
                    event_datetime = user_tz.localize(event_datetime)
                    
                    # Check if class ended 60 minutes ago
                    time_since_end = user_current_time - event_datetime
                    if timedelta(minutes=50) <= time_since_end <= timedelta(minutes=70):
                        
                        # Check if already sent for this event today
                        with self.db.get_connection() as conn:
                            sent = conn.execute(
                                """SELECT COUNT(*) as count FROM proactive_messages 
                                   WHERE user_id = ? AND message_type = 'class_end' 
                                   AND DATE(sent_at) = ?""",
                                (user['id'], user_current_time.date().isoformat())
                            ).fetchone()
                        
                        if sent['count'] == 0:
                            # Generate class end message
                            checkin_message = self.ai.generate_class_end_checkin(
                                user['name'], 
                                event.get('title', 'المحاضرة')
                            )
                            
                            await self._send_proactive_message(
                                user['telegram_id'], 
                                checkin_message, 
                                'class_end'
                            )
                            break
                            
                except ValueError:
                    continue
                    
        except Exception as e:
            logger.error(f"Error checking class ends for user {user['telegram_id']}: {e}")
    
    def _check_hydration_reminders(self):
        """Check for hydration reminders"""
        current_hour = datetime.now().hour
        
        # Only during day hours
        if not (10 <= current_hour <= 20):
            return
        
        try:
            # Get users who haven't logged water today
            with self.db.get_connection() as conn:
                users_needing_reminder = conn.execute(
                    """SELECT u.* FROM users u
                       LEFT JOIN water_logs wl ON u.id = wl.user_id AND wl.date = DATE('now')
                       WHERE u.allow_proactive = 1 
                       AND (wl.cups IS NULL OR wl.cups < 3)"""
                ).fetchall()
            
            for user in users_needing_reminder:
                asyncio.create_task(self._send_hydration_reminder(user))
                
        except Exception as e:
            logger.error(f"Error checking hydration reminders: {e}")
    
    async def _send_hydration_reminder(self, user):
        """Send hydration reminder to user"""
        try:
            # Check if already sent hydration reminder today
            today = datetime.now().date()
            with self.db.get_connection() as conn:
                sent_today = conn.execute(
                    """SELECT COUNT(*) as count FROM proactive_messages 
                       WHERE user_id = ? AND message_type = 'hydration' 
                       AND DATE(sent_at) = ?""",
                    (user['id'], today.isoformat())
                ).fetchone()
                
                if sent_today['count'] > 0:
                    return
            
            # Get current water intake
            today_water = self.db.get_today_water(user['id'])
            
            # Generate hydration message
            hydration_message = self.ai.generate_hydration_reminder(user['name'], today_water)
            
            await self._send_proactive_message(
                user['telegram_id'], 
                hydration_message, 
                'hydration'
            )
            
        except Exception as e:
            logger.error(f"Error sending hydration reminder to {user['telegram_id']}: {e}")
    
    def _check_evening_recaps(self):
        """Check for evening recaps"""
        current_hour = datetime.now().hour
        
        # Only during evening hours (9-10 PM)
        if not (21 <= current_hour <= 22):
            return
        
        try:
            with self.db.get_connection() as conn:
                users = conn.execute(
                    "SELECT * FROM users WHERE allow_proactive = 1"
                ).fetchall()
            
            for user in users:
                asyncio.create_task(self._send_evening_recap(user))
                
        except Exception as e:
            logger.error(f"Error checking evening recaps: {e}")
    
    async def _send_evening_recap(self, user):
        """Send evening recap to user"""
        try:
            # Check if already sent today
            today = datetime.now().date()
            with self.db.get_connection() as conn:
                sent_today = conn.execute(
                    """SELECT COUNT(*) as count FROM proactive_messages 
                       WHERE user_id = ? AND message_type = 'evening_recap' 
                       AND DATE(sent_at) = ?""",
                    (user['id'], today.isoformat())
                ).fetchone()
                
                if sent_today['count'] > 0:
                    return
            
            # Gather user data for recap
            recent_sessions = self.db.get_recent_sessions(user['id'], 1)
            subjects = self.db.get_user_subjects(user['id'])
            today_water = self.db.get_today_water(user['id'])
            
            user_data = {
                'name': user['name'],
                'study_sessions': [dict(s) for s in recent_sessions],
                'active_subjects': [dict(s) for s in subjects if s['status'] == 'in_progress'],
                'water_cups': today_water,
                'daily_activities': []  # Could be expanded
            }
            
            # Generate evening recap
            evening_message = self.ai.generate_evening_recap(user_data)
            
            await self._send_proactive_message(
                user['telegram_id'], 
                evening_message, 
                'evening_recap'
            )
            
        except Exception as e:
            logger.error(f"Error sending evening recap to {user['telegram_id']}: {e}")
    
    def _check_weekly_evaluations(self):
        """Check for weekly evaluations (Sundays)"""
        if datetime.now().weekday() != 6:  # Not Sunday
            return
        
        try:
            with self.db.get_connection() as conn:
                users = conn.execute(
                    "SELECT * FROM users WHERE allow_proactive = 1"
                ).fetchall()
            
            for user in users:
                asyncio.create_task(self._send_weekly_evaluation(user))
                
        except Exception as e:
            logger.error(f"Error checking weekly evaluations: {e}")
    
    async def _send_weekly_evaluation(self, user):
        """Send weekly evaluation to user"""
        try:
            # Check if already sent this week
            week_start = datetime.now() - timedelta(days=7)
            with self.db.get_connection() as conn:
                sent_this_week = conn.execute(
                    """SELECT COUNT(*) as count FROM proactive_messages 
                       WHERE user_id = ? AND message_type = 'weekly_evaluation' 
                       AND sent_at >= ?""",
                    (user['id'], week_start.isoformat())
                ).fetchone()
                
                if sent_this_week['count'] > 0:
                    return
            
            # Get weekly stats
            stats = self.db.get_user_stats(user['id'], 7)
            
            # Generate weekly evaluation
            evaluation_message = self.ai.generate_weekly_evaluation(stats)
            
            await self._send_proactive_message(
                user['telegram_id'], 
                evaluation_message, 
                'weekly_evaluation'
            )
            
        except Exception as e:
            logger.error(f"Error sending weekly evaluation to {user['telegram_id']}: {e}")
    
    def _run_adaptive_interventions(self):
        """Run adaptive interventions based on user behavior"""
        try:
            with self.db.get_connection() as conn:
                # Find users with inactive subjects
                inactive_users = conn.execute(
                    """SELECT u.*, s.name as subject_name, s.last_activity_ts 
                       FROM users u 
                       JOIN subjects s ON u.id = s.user_id 
                       WHERE u.allow_proactive = 1 
                       AND s.status = 'in_progress' 
                       AND s.last_activity_ts < datetime('now', '-3 days')
                       GROUP BY u.id
                       ORDER BY s.last_activity_ts ASC"""
                ).fetchall()
            
            for user_data in inactive_users:
                asyncio.create_task(self._send_adaptive_intervention(user_data))
                
        except Exception as e:
            logger.error(f"Error running adaptive interventions: {e}")
    
    async def _send_adaptive_intervention(self, user_data):
        """Send adaptive intervention message"""
        try:
            # Check if already sent intervention recently
            with self.db.get_connection() as conn:
                recent_interventions = conn.execute(
                    """SELECT COUNT(*) as count FROM proactive_messages 
                       WHERE user_id = ? AND message_type = 'adaptive_intervention' 
                       AND sent_at >= datetime('now', '-2 days')""",
                    (user_data['id'],)
                ).fetchone()
                
                if recent_interventions['count'] > 0:
                    return
            
            # Create adaptive message based on inactivity
            days_inactive = (datetime.now() - datetime.fromisoformat(user_data['last_activity_ts'])).days
            
            if days_inactive >= 3:
                intervention_msg = f"""مرحبا {user_data['name']} 👋

لاحظت إنك ما درست {user_data['subject_name']} من {days_inactive} أيام.

شرايك نبدأ بجلسة قصيرة؟ حتى 15 دقيقة تكفي!

استخدم /startsession {user_data['subject_name']} للبداية 💪"""
                
                await self._send_proactive_message(
                    user_data['telegram_id'], 
                    intervention_msg, 
                    'adaptive_intervention'
                )
                
        except Exception as e:
            logger.error(f"Error sending adaptive intervention: {e}")
    
    def _cleanup_old_data(self):
        """Clean up old data to keep database efficient"""
        try:
            with self.db.get_connection() as conn:
                # Clean old activity logs (keep 30 days)
                conn.execute(
                    "DELETE FROM user_activity WHERE timestamp < datetime('now', '-30 days')"
                )
                
                # Clean old proactive message logs (keep 30 days)
                conn.execute(
                    "DELETE FROM proactive_messages WHERE sent_at < datetime('now', '-30 days')"
                )
                
                # Clean old water logs (keep 90 days)
                conn.execute(
                    "DELETE FROM water_logs WHERE date < date('now', '-90 days')"
                )
                
                conn.commit()
                logger.info("Database cleanup completed")
                
        except Exception as e:
            logger.error(f"Error during database cleanup: {e}")

# Event-driven job triggers
class EventTriggeredJobs:
    def __init__(self, bot: Bot, db_manager: DatabaseManager, ai: GeminiAI):
        self.bot = bot
        self.db = db_manager
        self.ai = ai
    
    async def on_session_completed(self, user_id: int, session_data: Dict):
        """Trigger when study session is completed"""
        try:
            user = self.db.get_user_by_id(user_id)  # Need to add this method to DB
            if not user:
                return
            
            # Check if user needs encouragement based on session score
            score = session_data.get('score', 0)
            
            if score >= 8:
                # High score - congratulate
                congrats = self.ai.generate_motivation_message(
                    user['name'], 
                    f"جلسة ممتازة بتقييم {score}/10"
                )
            elif score <= 4:
                # Low score - encourage
                congrats = self.ai.generate_motivation_message(
                    user['name'], 
                    "محاولة جيدة، المرة القادمة أفضل"
                )
            else:
                # Medium score - motivate
                congrats = self.ai.generate_motivation_message(
                    user['name'], 
                    f"تقدم جيد بتقييم {score}/10"
                )
            
            # Send follow-up message after delay
            await asyncio.sleep(300)  # 5 minutes delay
            await self.bot.send_message(chat_id=user['telegram_id'], text=congrats)
            
        except Exception as e:
            logger.error(f"Error in session completion trigger: {e}")
    
    async def on_subject_added(self, user_id: int, subject_name: str):
        """Trigger when new subject is added"""
        try:
            user = self.db.get_user_by_id(user_id)
            if not user:
                return
            
            # Generate study plan after short delay
            await asyncio.sleep(60)  # 1 minute delay
            
            study_plan = self.ai.generate_subject_plan(subject_name, "مبتدئ")
            
            plan_message = f"📋 خطة دراسية لـ {subject_name}:\n\n{study_plan}"
            
            await self.bot.send_message(chat_id=user['telegram_id'], text=plan_message)
            
        except Exception as e:
            logger.error(f"Error in subject addition trigger: {e}")
    
    async def on_file_uploaded(self, user_id: int, file_data: Dict):
        """Trigger when file is uploaded"""
        try:
            user = self.db.get_user_by_id(user_id)
            if not user:
                return
            
            extracted_text = file_data.get('extracted_text')
            if not extracted_text:
                return
            
            # Generate additional insights after initial processing
            await asyncio.sleep(120)  # 2 minutes delay
            
            # Generate study suggestions based on content
            context = {
                'file_content': extracted_text[:1000],  # First 1000 chars
                'user_subjects': [s['name'] for s in self.db.get_user_subjects(user_id)]
            }
            
            suggestions = self.ai.generate_adaptive_response(
                "تم رفع ملف جديد", 
                {'user_data': dict(user), 'file_context': context}
            )
            
            await self.bot.send_message(
                chat_id=user['telegram_id'], 
                text=f"💡 اقتراحات إضافية للملف المرفوع:\n\n{suggestions}"
            )
            
        except Exception as e:
            logger.error(f"Error in file upload trigger: {e}")
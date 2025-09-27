"""
Main application file for RezeCoach Telegram Study & Wellness Assistant Bot
Complete production-grade implementation with Google Gemini AI integration
"""

import os
import logging
import asyncio
from typing import Dict, Any

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler, 
    CallbackQueryHandler, filters
)

from db import DatabaseManager
from ai import GeminiAI  
from handlers import RezeCoachHandlers, SETTING_NAME, SETTING_STAGE, SETTING_FACULTY, SETTING_MAJOR, SETTING_YEAR, SETTING_REMINDER_TIME, WAITING_SESSION_SUMMARY
from jobs import JobScheduler, EventTriggeredJobs
from utils import get_env_var, setup_logging

# Setup logging
setup_logging(level="INFO")
logger = logging.getLogger(__name__)

class RezeCoachBot:
    """Main bot class that coordinates all components"""
    
    def __init__(self):
        # Validate required environment variables
        self.bot_token = get_env_var('TELEGRAM_BOT_TOKEN', required=True)
        self.gemini_api_key = get_env_var('GEMINAI_API_KEY', required=True)
        
        # Initialize components
        logger.info("Initializing RezeCoach components...")
        
        # Database
        self.db = DatabaseManager()
        logger.info("✅ Database initialized")
        
        # AI
        self.ai = GeminiAI()
        logger.info("✅ Gemini AI initialized")
        
        # Bot application
        self.application = Application.builder().token(self.bot_token).build()
        self.bot = self.application.bot
        
        # Handlers
        self.handlers = RezeCoachHandlers(self.db, self.ai)
        logger.info("✅ Message handlers initialized")
        
        # Job scheduler
        self.scheduler = JobScheduler(self.bot, self.db, self.ai)
        logger.info("✅ Job scheduler initialized")
        
        # Event triggers
        self.event_triggers = EventTriggeredJobs(self.bot, self.db, self.ai)
        logger.info("✅ Event triggers initialized")
        
        self._setup_handlers()
        logger.info("✅ All handlers registered")
    
    def _setup_handlers(self):
        """Setup all command and message handlers"""
        
        # Onboarding conversation handler
        onboarding_handler = ConversationHandler(
            entry_points=[CommandHandler("start", self.handlers.start_command)],
            states={
                SETTING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.set_name)],
                SETTING_STAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.set_stage)],
                SETTING_FACULTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.set_faculty)],
                SETTING_MAJOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.set_major)],
                SETTING_YEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.set_year)],
                SETTING_REMINDER_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.set_reminder_time)],
            },
            fallbacks=[CommandHandler("cancel", self.handlers.cancel_command)]
        )
        
        # Session summary conversation handler
        session_summary_handler = ConversationHandler(
            entry_points=[CommandHandler("endsession", self.handlers.end_session_command)],
            states={
                WAITING_SESSION_SUMMARY: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.session_summary_received)]
            },
            fallbacks=[CommandHandler("cancel", self.handlers.cancel_command)]
        )
        
        # Register all handlers
        handlers_list = [
            # Conversation handlers (must be first)
            onboarding_handler,
            session_summary_handler,
            
            # Command handlers
            CommandHandler("help", self.handlers.help_command),
            CommandHandler("addsubject", self.handlers.add_subject_command),
            CommandHandler("subjects", self.handlers.list_subjects_command),
            CommandHandler("setprogress", self.handlers.set_progress_command),
            CommandHandler("startsession", self.handlers.start_session_command),
            CommandHandler("water", self.handlers.water_command),
            CommandHandler("waterlog", self.handlers.water_log_command),
            CommandHandler("today", self.handlers.today_command),
            CommandHandler("stats", self.handlers.stats_command),
            CommandHandler("profile", self.handlers.profile_command),
            
            # Additional command handlers
            CommandHandler("setstage", self._handle_set_stage),
            CommandHandler("setfaculty", self._handle_set_faculty),
            CommandHandler("setmajor", self._handle_set_major),
            CommandHandler("settime", self._handle_set_time),
            CommandHandler("toggleproactive", self._handle_toggle_proactive),
            CommandHandler("setschedule", self._handle_set_schedule),
            CommandHandler("timezone", self._handle_set_timezone),
            CommandHandler("export", self._handle_export_data),
            CommandHandler("reset", self._handle_reset_profile),
            
            # File handlers
            MessageHandler(filters.Document.ALL, self.handlers.handle_document),
            
            # Callback query handler
            CallbackQueryHandler(self.handlers.handle_callback_query),
            
            # General message handler (must be last)
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handlers.handle_message),
        ]
        
        for handler in handlers_list:
            self.application.add_handler(handler)
        
        # Error handler
        self.application.add_error_handler(self.handlers.error_handler)
    
    async def _handle_set_stage(self, update: Update, context):
        """Handle /setstage command"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        if not context.args:
            await update.message.reply_text("استخدم: /setstage المرحلة_الدراسية")
            return
        
        stage = ' '.join(context.args)
        success = self.db.update_user(user['telegram_id'], study_stage=stage)
        
        if success:
            await update.message.reply_text(f"تم تحديث المرحلة الدراسية إلى: {stage}")
        else:
            await update.message.reply_text("صار خطأ، جرب مرة ثانية")
    
    async def _handle_set_faculty(self, update: Update, context):
        """Handle /setfaculty command"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        if not context.args:
            await update.message.reply_text("استخدم: /setfaculty اسم_الكلية")
            return
        
        faculty = ' '.join(context.args)
        success = self.db.update_user(user['telegram_id'], faculty=faculty)
        
        if success:
            await update.message.reply_text(f"تم تحديث الكلية إلى: {faculty}")
        else:
            await update.message.reply_text("صار خطأ، جرب مرة ثانية")
    
    async def _handle_set_major(self, update: Update, context):
        """Handle /setmajor command"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        if not context.args:
            await update.message.reply_text("استخدم: /setmajor التخصص")
            return
        
        major = ' '.join(context.args)
        success = self.db.update_user(user['telegram_id'], major=major)
        
        if success:
            await update.message.reply_text(f"تم تحديث التخصص إلى: {major}")
        else:
            await update.message.reply_text("صار خطأ، جرب مرة ثانية")
    
    async def _handle_set_time(self, update: Update, context):
        """Handle /settime command"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        if not context.args:
            await update.message.reply_text("استخدم: /settime HH:MM\nمثال: /settime 09:00")
            return
        
        from utils import TimezoneManager, InputValidator
        
        time_input = context.args[0]
        reminder_time = TimezoneManager.parse_time_expression(time_input)
        
        if not reminder_time or not InputValidator.validate_time(reminder_time):
            await update.message.reply_text("صيغة الوقت غير صحيحة. استخدم: HH:MM\nمثال: 09:00")
            return
        
        success = self.db.update_user(user['telegram_id'], daily_reminder_time=reminder_time)
        
        if success:
            await update.message.reply_text(f"تم تحديث وقت التذكير اليومي إلى: {reminder_time}")
        else:
            await update.message.reply_text("صار خطأ، جرب مرة ثانية")
    
    async def _handle_toggle_proactive(self, update: Update, context):
        """Handle /toggleproactive command"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        if not context.args or context.args[0].lower() not in ['on', 'off', 'تشغيل', 'إيقاف']:
            current_status = "مفعل" if user['allow_proactive'] else "معطل"
            await update.message.reply_text(
                f"الرسائل التلقائية حالياً: {current_status}\n\n"
                "لتغيير الإعداد استخدم:\n"
                "/toggleproactive on - للتفعيل\n"
                "/toggleproactive off - للإيقاف"
            )
            return
        
        enable = context.args[0].lower() in ['on', 'تشغيل']
        success = self.db.update_user(user['telegram_id'], allow_proactive=enable)
        
        if success:
            status = "مفعل" if enable else "معطل"
            await update.message.reply_text(f"تم تحديث الرسائل التلقائية إلى: {status}")
        else:
            await update.message.reply_text("صار خطأ، جرب مرة ثانية")
    
    async def _handle_set_schedule(self, update: Update, context):
        """Handle /setschedule command"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        schedule_help = """📅 لإعداد الجدول الأسبوعي:

يمكنك إرسال الجدول بصيغة JSON أو إضافة فعالية واحدة:

**إضافة فعالية واحدة:**
/setschedule يوم وقت عنوان
مثال: /setschedule الاثنين 09:00 محاضرة الرياضيات

**الأيام المقبولة:**
الأحد، الاثنين، الثلاثاء، الأربعاء، الخميس، الجمعة، السبت

**أو أرسل الجدول كاملاً بصيغة JSON**"""
        
        if not context.args:
            await update.message.reply_text(schedule_help)
            return
        
        # Simple single event addition
        if len(context.args) >= 3:
            day_names = {
                'الأحد': 6, 'الاثنين': 0, 'الثلاثاء': 1, 'الأربعاء': 2, 
                'الخميس': 3, 'الجمعة': 4, 'السبت': 5,
                'أحد': 6, 'اثنين': 0, 'ثلاثاء': 1, 'أربعاء': 2, 
                'خميس': 3, 'جمعة': 4, 'سبت': 5
            }
            
            day_str = context.args[0]
            time_str = context.args[1] 
            title = ' '.join(context.args[2:])
            
            day_num = day_names.get(day_str)
            if day_num is None:
                await update.message.reply_text(f"يوم غير صحيح: {day_str}\nاستخدم: الأحد، الاثنين، الثلاثاء، إلخ...")
                return
            
            from utils import InputValidator
            if not InputValidator.validate_time(time_str):
                await update.message.reply_text(f"وقت غير صحيح: {time_str}\nاستخدم صيغة: HH:MM")
                return
            
            # Get existing schedule for the day
            existing_events = self.db.get_daily_schedule(user['id'], day_num)
            
            # Add new event
            new_event = {'time': time_str, 'title': title}
            existing_events.append(new_event)
            
            # Sort by time
            existing_events.sort(key=lambda x: x['time'])
            
            # Save updated schedule
            success = self.db.set_weekly_schedule(user['id'], day_num, existing_events)
            
            if success:
                await update.message.reply_text(f"✅ تمت إضافة الفعالية:\n📅 {day_str} {time_str}\n📝 {title}")
            else:
                await update.message.reply_text("صار خطأ، جرب مرة ثانية")
        else:
            await update.message.reply_text(schedule_help)
    
    async def _handle_set_timezone(self, update: Update, context):
        """Handle /timezone command"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        if not context.args:
            await update.message.reply_text(
                f"المنطقة الزمنية الحالية: {user['timezone']}\n\n"
                "لتغيير المنطقة الزمنية استخدم:\n"
                "/timezone Asia/Baghdad\n"
                "/timezone Asia/Riyadh\n"
                "/timezone Europe/London\n"
                "إلخ..."
            )
            return
        
        timezone_str = context.args[0]
        
        # Validate timezone
        from utils import TimezoneManager
        try:
            TimezoneManager.get_user_timezone(timezone_str)
        except:
            await update.message.reply_text(f"منطقة زمنية غير صحيحة: {timezone_str}")
            return
        
        success = self.db.update_user(user['telegram_id'], timezone=timezone_str)
        
        if success:
            await update.message.reply_text(f"تم تحديث المنطقة الزمنية إلى: {timezone_str}")
        else:
            await update.message.reply_text("صار خطأ، جرب مرة ثانية")
    
    async def _handle_export_data(self, update: Update, context):
        """Handle /export command"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        from utils import DataExporter
        import json
        
        try:
            user_data = DataExporter.export_user_data(self.db, user['id'])
            
            if user_data:
                # Convert to JSON string
                json_data = json.dumps(user_data, ensure_ascii=False, indent=2)
                
                # Send as file
                from io import BytesIO
                file_buffer = BytesIO(json_data.encode('utf-8'))
                file_buffer.name = f"rezecoach_data_{user['name']}_{user_data['exported_at'][:10]}.json"
                
                await update.message.reply_document(
                    document=file_buffer,
                    caption="📤 تصدير بياناتك من RezeCoach\n\nاحتفظ بهذا الملف كنسخة احتياطية!"
                )
            else:
                await update.message.reply_text("صار خطأ في تصدير البيانات")
                
        except Exception as e:
            logger.error(f"Export error: {e}")
            await update.message.reply_text("صار خطأ، جرب مرة ثانية")
    
    async def _handle_reset_profile(self, update: Update, context):
        """Handle /reset command"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = [
            [
                InlineKeyboardButton("✅ نعم، احذف كل شيء", callback_data=f"reset_confirm_{user['id']}"),
                InlineKeyboardButton("❌ لا، أبقِ البيانات", callback_data="reset_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ **تحذير: إعادة تعيين البيانات**\n\n"
            "هذا الإجراء سيحذف جميع بياناتك:\n"
            "• الملف الشخصي\n"
            "• المواد والتقدم\n"
            "• جلسات الدراسة\n"
            "• سجل المياه\n"
            "• الجدول الأسبوعي\n"
            "• الملفات المرفوعة\n\n"
            "**هل أنت متأكد؟**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    async def _get_user_or_prompt(self, update: Update):
        """Helper to get user or prompt for setup"""
        telegram_id = str(update.effective_user.id)
        user = self.db.get_user(telegram_id)
        
        if not user:
            await update.message.reply_text("مرحباً! استخدم /start أولاً لإعداد حسابك.")
            return None
        
        return dict(user)
    
    def run(self):
        """Start the bot and all services"""
        try:
            logger.info("🚀 Starting RezeCoach Bot...")
            
            # Start job scheduler
            self.scheduler.start()
            logger.info("✅ Job scheduler started")
            
            # Start bot polling
            logger.info("✅ Starting bot polling...")
            self.application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            
        except KeyboardInterrupt:
            logger.info("👋 Bot stopped by user")
        except Exception as e:
            logger.error(f"❌ Bot error: {e}")
            raise
        finally:
            # Cleanup
            if hasattr(self, 'scheduler'):
                self.scheduler.stop()
            logger.info("✅ Cleanup completed")

def main():
    """Main entry point"""
    logger.info("""
    
🤖 RezeCoach - Telegram Study & Wellness Assistant Bot
==================================================

🧠 AI-Powered Study Assistant with Google Gemini
📚 Complete Study Session Management
💧 Health & Wellness Tracking
📅 Smart Scheduling & Reminders
🎯 Adaptive Learning Interventions
🇮🇶 Arabic (Iraqi Dialect) Interface

Starting bot initialization...
    """)
    
    # Validate environment
    required_vars = ['TELEGRAM_BOT_TOKEN', 'GEMINAI_API_KEY']
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        logger.error(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please set the following environment variables:")
        for var in missing_vars:
            logger.error(f"   export {var}='your_value_here'")
        return
    
    # Create and run bot
    bot = RezeCoachBot()
    bot.run()

if __name__ == "__main__":
    main()
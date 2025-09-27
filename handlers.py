"""
Telegram bot message handlers for RezeCoach
Handles all user interactions, commands, and message processing
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import re
import json

from db import DatabaseManager
from ai import GeminiAI
from utils import TimezoneManager, MessageFormatter, InputValidator, FileHandler

logger = logging.getLogger(__name__)

# Conversation states
(SETTING_NAME, SETTING_STAGE, SETTING_FACULTY, SETTING_MAJOR, 
 SETTING_YEAR, SETTING_REMINDER_TIME, WAITING_SESSION_SUMMARY) = range(7)

class RezeCoachHandlers:
    def __init__(self, db_manager: DatabaseManager, ai: GeminiAI):
        self.db = db_manager
        self.ai = ai
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle /start command and begin user onboarding"""
        telegram_id = str(update.effective_user.id)
        user = self.db.get_user(telegram_id)
        
        if user:
            # Existing user
            welcome_msg = f"أهلا وسهلا {user['name']}! 👋\n\nأنا RezeCoach، مساعدك في الدراسة والصحة.\n\nاستخدم /help لمعرفة الأوامر المتاحة."
            await update.message.reply_text(welcome_msg)
            return ConversationHandler.END
        else:
            # New user - start onboarding
            welcome_msg = """أهلا وسهلا! 🌟

أنا RezeCoach، مساعدك الذكي للدراسة والصحة!

راح أساعدك في:
📚 تنظيم جدول الدراسة
💧 تذكيرات شرب الماء  
📈 تتبع التقدم الأكاديمي
🎯 وضع خطط دراسية ذكية

خلنا نبدأ بالتعرف عليك!

شنو اسمك؟"""
            
            await update.message.reply_text(welcome_msg)
            return SETTING_NAME
    
    async def set_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Set user name during onboarding"""
        name = update.message.text.strip()
        context.user_data['name'] = name
        
        response = f"أهلا {name}! 😊\n\nشنو مرحلتك الدراسية؟\n\n• البكالوريوس\n• الماجستير\n• الدكتوراه\n• الثانوية\n• غير ذلك"
        await update.message.reply_text(response)
        return SETTING_STAGE
    
    async def set_stage(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Set study stage during onboarding"""
        stage = update.message.text.strip()
        context.user_data['study_stage'] = stage
        
        response = f"زين! {stage} مرحلة مهمة 📚\n\nشنو كليتك أو تخصصك الرئيسي؟"
        await update.message.reply_text(response)
        return SETTING_FACULTY
    
    async def set_faculty(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Set faculty during onboarding"""
        faculty = update.message.text.strip()
        context.user_data['faculty'] = faculty
        
        response = f"ممتاز! {faculty} تخصص حلو 🎓\n\nشنو تخصصك الفرعي أو قسمك بالتحديد؟"
        await update.message.reply_text(response)
        return SETTING_MAJOR
    
    async def set_major(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Set major during onboarding"""
        major = update.message.text.strip()
        context.user_data['major'] = major
        
        response = f"تمام! {major} تخصص رائع 💪\n\nشنو سنتك الدراسية؟ (مثلا: السنة الثانية، السنة الأولى، إلخ...)"
        await update.message.reply_text(response)
        return SETTING_YEAR
    
    async def set_year(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Set academic year during onboarding"""
        year = update.message.text.strip()
        context.user_data['academic_year'] = year
        
        response = """حلو! آخر شي 🕐

متى تحب أذكرك بالدراسة كل يوم؟

اكتب الوقت بالشكل هذا: 09:00
أو اكتب: الصباح، الظهر، المساء، الليل"""
        
        await update.message.reply_text(response)
        return SETTING_REMINDER_TIME
    
    async def set_reminder_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Complete onboarding with reminder time"""
        time_input = update.message.text.strip()
        reminder_time = TimezoneManager.parse_time_expression(time_input)
        
        if not reminder_time:
            await update.message.reply_text("الوقت مو واضح، جرب مرة ثانية:\n\nمثال: 09:00 أو اكتب: الصباح")
            return SETTING_REMINDER_TIME
        
        # Create user in database
        telegram_id = str(update.effective_user.id)
        user_data = context.user_data
        
        try:
            user_id = self.db.create_user(
                telegram_id=telegram_id,
                name=user_data['name']
            )
            
            # Update user profile
            self.db.update_user(
                telegram_id=telegram_id,
                study_stage=user_data['study_stage'],
                faculty=user_data['faculty'],
                major=user_data['major'],
                academic_year=user_data['academic_year'],
                daily_reminder_time=reminder_time
            )
            
            # Log activity
            self.db.log_activity(user_id, 'onboarding_completed', user_data)
            
            completion_msg = f"""تمام! خلصنا الإعدادات! ✅

ملخص ملفك الشخصي:
👤 الاسم: {user_data['name']}
🎓 المرحلة: {user_data['study_stage']}
🏫 الكلية: {user_data['faculty']}  
📚 التخصص: {user_data['major']}
📅 السنة: {user_data['academic_year']}
⏰ التذكير: {reminder_time}

راح أساعدك من اليوم بتنظيم دراستك وصحتك! 💪

استخدم /help لمعرفة كل الأوامر المتاحة.

خلنا نبدأ بإضافة مادة دراسية؟ استخدم:
/addsubject اسم_المادة"""
            
            await update.message.reply_text(completion_msg)
            
        except Exception as e:
            logger.error(f"Error completing onboarding: {e}")
            await update.message.reply_text("صار خطأ، جرب مرة ثانية بعد قليل.")
        
        # Clear user data
        context.user_data.clear()
        return ConversationHandler.END
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show help message with all available commands"""
        help_text = """🤖 أوامر RezeCoach:

📚 **إدارة المواد:**
/addsubject <اسم المادة> - إضافة مادة جديدة
/subjects - عرض جميع المواد
/setprogress <مادة> <قسم> - تحديث التقدم

📝 **جلسات الدراسة:**  
/startsession [مادة] - بدء جلسة دراسة
/endsession <ملخص> - إنهاء الجلسة

💧 **الصحة والعافية:**
/water [عدد] - تسجيل شرب الماء
/waterlog - عرض سجل المياه

📅 **الجدول والتنظيم:**
/setschedule - تحديد الجدول الأسبوعي  
/today - جدول اليوم
/stats - إحصائيات الأسبوع

⚙️ **الإعدادات:**
/settime <وقت> - وقت التذكير اليومي
/timezone <منطقة> - المنطقة الزمنية
/toggleproactive - تفعيل/إيقاف الرسائل التلقائية
/profile - عرض الملف الشخصي

📤 **أخرى:**
/export - تصدير البيانات
/reset - إعادة تعيين المعلومات

أرسل أي رسالة وراح أرد عليك بذكاء! 🧠"""
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def add_subject_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add new subject"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        # Parse arguments
        args = context.args
        if not args:
            await update.message.reply_text("استخدم: /addsubject اسم_المادة [الأولوية 1-5]")
            return
        
        subject_name = args[0]
        priority = 3  # default
        
        if len(args) > 1:
            priority = InputValidator.validate_priority(args[1])
            if priority is None:
                await update.message.reply_text("الأولوية يجب تكون رقم من 1 إلى 5")
                return
        
        try:
            subject_id = self.db.add_subject(user['id'], subject_name, priority)
            self.db.log_activity(user['id'], 'subject_added', {'subject_name': subject_name})
            
            priority_stars = "⭐" * priority
            await update.message.reply_text(
                f"تمام! أضيفت المادة:\n📚 {subject_name} {priority_stars}\n\nاستخدم /startsession {subject_name} لبدء دراستها!"
            )
        except Exception as e:
            logger.error(f"Error adding subject: {e}")
            await update.message.reply_text("صار خطأ، جرب مرة ثانية.")
    
    async def list_subjects_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List user subjects"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        subjects = self.db.get_user_subjects(user['id'])
        text = MessageFormatter.format_subjects_list([dict(s) for s in subjects])
        await update.message.reply_text(text)
    
    async def set_progress_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set subject progress"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("استخدم: /setprogress اسم_المادة القسم_الحالي")
            return
        
        subject_name = args[0]
        current_section = ' '.join(args[1:])
        
        success = self.db.update_subject_progress(user['id'], subject_name, current_section)
        
        if success:
            self.db.log_activity(user['id'], 'progress_updated', {
                'subject': subject_name, 
                'section': current_section
            })
            await update.message.reply_text(f"تم تحديث التقدم!\n📚 {subject_name}\n📖 {current_section}")
        else:
            await update.message.reply_text(f"ما لقيت المادة: {subject_name}\nتأكد من الاسم أو أضفها بـ /addsubject")
    
    async def start_session_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start study session"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        # Check for active session
        active_session = self.db.get_active_session(user['id'])
        if active_session:
            await update.message.reply_text("عندك جلسة دراسة نشطة! اكملها أو استخدم /endsession لإنهائها")
            return
        
        subject_id = None
        subject_name = "عام"
        
        if context.args:
            subject_name = context.args[0]
            subject = self.db.get_subject(user['id'], subject_name)
            if subject:
                subject_id = subject['id']
            else:
                await update.message.reply_text(f"ما لقيت المادة: {subject_name}\nراح أبدأ جلسة عامة.")
                subject_name = "عام"
        
        try:
            session_id = self.db.start_study_session(user['id'], subject_id)
            context.user_data['active_session_id'] = session_id
            
            self.db.log_activity(user['id'], 'session_started', {'subject': subject_name})
            
            keyboard = [
                [InlineKeyboardButton("⏹ إنهاء الجلسة", callback_data="end_session")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"🚀 بدأت جلسة دراسة جديدة!\n📚 المادة: {subject_name}\n⏰ الوقت: {datetime.now().strftime('%H:%M')}\n\nبالتوفيق! 💪",
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Error starting session: {e}")
            await update.message.reply_text("صار خطأ، جرب مرة ثانية.")
    
    async def end_session_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """End study session"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        active_session = self.db.get_active_session(user['id'])
        if not active_session:
            await update.message.reply_text("ما عندك جلسة نشطة حالياً.")
            return
        
        # Ask for summary
        await update.message.reply_text("اكتب ملخص سريع عن الجلسة:")
        context.user_data['ending_session_id'] = active_session['id']
        return WAITING_SESSION_SUMMARY
    
    async def session_summary_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle session summary input"""
        session_id = context.user_data.get('ending_session_id')
        if not session_id:
            return ConversationHandler.END
        
        summary = update.message.text.strip()
        
        # Ask for score with inline keyboard
        keyboard = []
        for i in range(1, 11):
            keyboard.append([InlineKeyboardButton(f"{i}/10 {'⭐' * i}", callback_data=f"score_{session_id}_{i}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.user_data['session_summary'] = summary
        
        await update.message.reply_text(
            "شلون تقيم هذه الجلسة من 1 إلى 10؟",
            reply_markup=reply_markup
        )
        
        return ConversationHandler.END
    
    async def water_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Log water intake"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        cups = 1
        if context.args:
            try:
                cups = max(1, int(context.args[0]))
            except ValueError:
                await update.message.reply_text("استخدم: /water [عدد_الأكواب]")
                return
        
        self.db.log_water(user['id'], cups)
        total_today = self.db.get_today_water(user['id'])
        
        water_msg = MessageFormatter.format_water_intake(total_today)
        motivational_msg = self.ai.generate_motivation_message(user['name'], f"شرب {cups} كاس ماء")
        
        await update.message.reply_text(f"{water_msg}\n\n{motivational_msg}")
        self.db.log_activity(user['id'], 'water_logged', {'cups': cups, 'total_today': total_today})
    
    async def water_log_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show water intake log"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        today_water = self.db.get_today_water(user['id'])
        formatted_msg = MessageFormatter.format_water_intake(today_water)
        
        await update.message.reply_text(f"سجل المياه لليوم:\n{formatted_msg}")
    
    async def today_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show today's schedule"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        today = datetime.now().weekday()  # 0=Monday
        schedule = self.db.get_daily_schedule(user['id'], today)
        
        formatted_schedule = MessageFormatter.format_weekly_schedule(schedule)
        
        # Add study session info
        recent_sessions = self.db.get_recent_sessions(user['id'], 1)
        session_text = ""
        if recent_sessions:
            session_text = f"\n\nجلسات اليوم:\n{MessageFormatter.format_study_session(dict(recent_sessions[0]))}"
        
        await update.message.reply_text(f"{formatted_schedule}{session_text}")
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show weekly statistics"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        stats = self.db.get_user_stats(user['id'], 7)
        weekly_summary = self.ai.generate_weekly_evaluation(stats)
        
        await update.message.reply_text(f"📊 إحصائيات الأسبوع:\n\n{weekly_summary}")
    
    async def profile_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user profile"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        profile_text = f"""👤 الملف الشخصي:

📛 الاسم: {user['name'] or 'غير محدد'}
🎓 المرحلة: {user['study_stage'] or 'غير محدد'}
🏫 الكلية: {user['faculty'] or 'غير محدد'}
📚 التخصص: {user['major'] or 'غير محدد'}
📅 السنة: {user['academic_year'] or 'غير محدد'}
⏰ التذكير اليومي: {user['daily_reminder_time']}
🌍 المنطقة الزمنية: {user['timezone']}
📱 الرسائل التلقائية: {'مفعل' if user['allow_proactive'] else 'معطل'}

تاريخ الانضمام: {user['created_at'][:10]}"""
        
        await update.message.reply_text(profile_text)
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle uploaded documents"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        document = update.message.document
        if not document:
            return
        
        try:
            # Download file
            file = await context.bot.get_file(document.file_id)
            file_content = await file.download_as_bytearray()
            
            # Save file
            filepath = FileHandler.save_uploaded_file(
                file_content, document.file_name, user['id']
            )
            
            if filepath:
                # Extract text if possible
                extracted_text = FileHandler.extract_text_from_file(filepath)
                
                # Save to database
                self.db.save_file(
                    user['id'], document.file_id, filepath, 
                    document.mime_type, extracted_text
                )
                
                # Generate AI summary
                if extracted_text:
                    summary = self.ai.summarize_notes(extracted_text, "ملاحظات مرفوعة")
                    await update.message.reply_text(f"📄 تم رفع الملف!\n\n{summary}")
                else:
                    await update.message.reply_text("📄 تم رفع الملف بنجاح! لكن ما قدرت أستخرج النص منه.")
                
                self.db.log_activity(user['id'], 'file_uploaded', {
                    'filename': document.file_name,
                    'size': document.file_size
                })
            else:
                await update.message.reply_text("صار خطأ في رفع الملف، جرب مرة ثانية.")
                
        except Exception as e:
            logger.error(f"Error handling document: {e}")
            await update.message.reply_text("صار خطأ، جرب مرة ثانية.")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages with AI response"""
        user = await self._get_user_or_prompt(update)
        if not user:
            return
        
        user_message = update.message.text
        
        # Build context for AI
        recent_activity = self.db.get_recent_activity(user['id'], 24)
        active_session = self.db.get_active_session(user['id'])
        subjects = self.db.get_user_subjects(user['id'])
        
        ai_context = {
            'user_data': dict(user),
            'recent_activity': [dict(a) for a in recent_activity],
            'current_state': {
                'active_session': dict(active_session) if active_session else None,
                'subjects': [dict(s) for s in subjects]
            }
        }
        
        # Generate AI response
        response = self.ai.generate_adaptive_response(user_message, ai_context)
        await update.message.reply_text(response)
        
        # Log activity
        self.db.log_activity(user['id'], 'message_sent', {'message': user_message[:100]})
        
        # Trigger contextual actions based on keywords
        await self._handle_contextual_triggers(update, context, user_message, user)
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == "end_session":
            # Handle end session button
            user = await self._get_user_or_prompt(update)
            if user:
                active_session = self.db.get_active_session(user['id'])
                if active_session:
                    await query.message.reply_text("اكتب ملخص سريع عن الجلسة:")
                    context.user_data['ending_session_id'] = active_session['id']
        
        elif data.startswith("score_"):
            # Handle session scoring
            parts = data.split("_")
            session_id = int(parts[1])
            score = int(parts[2])
            
            summary = context.user_data.get('session_summary', '')
            
            # End the session
            success = self.db.end_study_session(session_id, summary, score)
            
            if success:
                score_emoji = "⭐" * score
                completion_msg = f"🎉 تم إنهاء الجلسة بنجاح!\n\n📝 الملخص: {summary}\n⭐ التقييم: {score}/10 {score_emoji}\n\nأحسنت! استمر على هذا المنوال 💪"
                
                await query.message.reply_text(completion_msg)
                
                # Generate motivational message
                user = await self._get_user_or_prompt(update)
                if user:
                    motivation = self.ai.generate_motivation_message(user['name'], f"أكمل جلسة دراسية بتقييم {score}/10")
                    await query.message.reply_text(motivation)
                    
                    self.db.log_activity(user['id'], 'session_completed', {
                        'session_id': session_id,
                        'score': score,
                        'summary': summary
                    })
            
            # Clean up user data
            context.user_data.pop('ending_session_id', None)
            context.user_data.pop('session_summary', None)
    
    async def _get_user_or_prompt(self, update: Update) -> Optional[Dict]:
        """Get user from DB or prompt to start"""
        telegram_id = str(update.effective_user.id)
        user = self.db.get_user(telegram_id)
        
        if not user:
            await update.message.reply_text("مرحباً! استخدم /start أولاً لإعداد حسابك.")
            return None
        
        return dict(user)
    
    async def _handle_contextual_triggers(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                        message: str, user: Dict):
        """Handle contextual message triggers"""
        message_lower = message.lower()
        
        # Home arrival trigger
        if any(word in message for word in ['رجعت', 'وصلت', 'البيت']):
            # Check water intake
            today_water = self.db.get_today_water(user['id'])
            if today_water < 3:  # Less than 3 cups
                water_reminder = self.ai.generate_hydration_reminder(user['name'], today_water)
                await update.message.reply_text(water_reminder)
        
        # Tiredness trigger
        elif any(word in message for word in ['تعبان', 'متعب', 'مو قادر']):
            motivation = self.ai.generate_motivation_message(user['name'])
            await update.message.reply_text(motivation)
        
        # Success/completion trigger  
        elif any(word in message for word in ['خلصت', 'انتهيت', 'كملت']):
            congrats = self.ai.generate_motivation_message(user['name'], 'إكمال مهمة')
            await update.message.reply_text(congrats)
        
        # Study question trigger
        elif any(word in message for word in ['شلون', 'كيف', 'وين', 'شنو']):
            subjects = self.db.get_user_subjects(user['id'])
            if subjects:
                active_subjects = [s['name'] for s in subjects if s['status'] == 'in_progress']
                if active_subjects:
                    suggestion = f"جرب تركز على: {', '.join(active_subjects[:2])}"
                    await update.message.reply_text(suggestion)

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancel current conversation"""
        await update.message.reply_text("تم الإلغاء! استخدم /help للمساعدة.")
        context.user_data.clear()
        return ConversationHandler.END
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Update {update} caused error {context.error}")
        
        if update.effective_message:
            await update.effective_message.reply_text(
                "صار خطأ غير متوقع 😅\n\nجرب مرة ثانية أو استخدم /help للمساعدة."
            )
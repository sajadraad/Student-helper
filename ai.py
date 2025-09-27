"""
Google Gemini AI integration for RezeCoach
Handles all AI-powered responses and content generation
"""

import google.generativeai as genai
import os
import logging
import time
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)

class GeminiAI:
    def __init__(self):
        self.api_key = os.environ.get('GEMINAI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINAI_API_KEY environment variable is required")
        
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 1  # seconds between requests
        
        # System prompts in Arabic (Iraqi dialect)
        self.system_prompts = {
            'morning_greeting': """أنت RezeCoach، مساعد ذكي للدراسة والصحة. اكتب تحية صباحية بالعامية العراقية، ودية ومحفزة. 
                               استخدم اسم الطالب إذا متوفر. اجعل الرسالة قصيرة (جملة واحدة أو اثنتين) ومناسبة للوقت.""",
            
            'class_end_checkin': """أنت RezeCoach. اكتب رسالة تسأل فيها الطالب عن حاله بعد انتهاء المحاضرة. 
                                 استخدم العامية العراقية، كن ودود ومهتم. اسأل إذا وصل البيت وإذا كان بحاجة لشيء.""",
            
            'hydration_reminder': """أنت RezeCoach. ذكّر الطالب بشرب الماء بطريقة ودية وبالعامية العراقية. 
                                  اجعل التذكير خفيف الدم وليس متزمت.""",
            
            'evening_recap': """أنت RezeCoach. اكتب ملخص مسائي لنشاطات الطالب اليوم بالعامية العراقية. 
                              يجب أن يحتوي على: 
                              1. ملخص مختصر (3 جمل)
                              2. 5 flashcards للمراجعة
                              3. خطة صغيرة لليوم التالي
                              اجعل الأسلوب محفز وإيجابي.""",
            
            'weekly_evaluation': """أنت RezeCoach. اكتب تقييم أسبوعي شامل بالعامية العراقية يحتوي على:
                                  1. 3 نقاط قوة
                                  2. 3 نقاط تحتاج تحسين
                                  3. خطة للأسبوع الجديد (7 أيام)
                                  4. رسالة تحفيزية
                                  اجعل التقييم صادق ومفيد.""",
            
            'notes_summary': """أنت RezeCoach. لخّص الملاحظات المرفوعة بالعامية العراقية:
                              1. 6 نقاط رئيسية
                              2. 3 flashcards مهمة
                              3. اقتراح مهمة للمراجعة
                              اجعل الملخص واضح ومفيد للدراسة.""",
            
            'adaptive_response': """أنت RezeCoach. رد على الطالب بناءً على السياق المعطى. 
                                  استخدم العامية العراقية، كن ذكي ومتفهم، واقترح خطوات عملية مناسبة للموقف."""
        }
    
    def _rate_limit(self):
        """Simple rate limiting to avoid API overuse"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def _make_request(self, prompt: str, context: Dict = None, retry_count: int = 3) -> Optional[str]:
        """Make request to Gemini with retry logic"""
        self._rate_limit()
        
        # Build full prompt with context
        full_prompt = prompt
        if context:
            context_str = json.dumps(context, ensure_ascii=False, indent=2)
            full_prompt += f"\n\nالسياق:\n{context_str}"
        
        for attempt in range(retry_count):
            try:
                response = self.model.generate_content(
                    full_prompt,
                    generation_config={
                        'temperature': 0.7,
                        'max_output_tokens': 1024,
                    }
                )
                
                if response.text:
                    return response.text.strip()
                else:
                    logger.warning(f"Empty response from Gemini on attempt {attempt + 1}")
                    
            except Exception as e:
                logger.error(f"Gemini API error on attempt {attempt + 1}: {e}")
                if attempt < retry_count - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error("Max retries exceeded for Gemini API")
        
        return None
    
    def generate_morning_greeting(self, user_name: str, daily_events: List[str] = None) -> str:
        """Generate morning greeting message"""
        context = {
            'اسم_الطالب': user_name,
            'فعاليات_اليوم': daily_events or []
        }
        
        response = self._make_request(self.system_prompts['morning_greeting'], context)
        if response:
            return response
        
        # Fallback message
        return f"صباح الخير {user_name} 🌞 يوم جديد وفرص جديدة! يلا نبدأ بنشاط!"
    
    def generate_class_end_checkin(self, user_name: str, subject_name: str = None) -> str:
        """Generate post-class check-in message"""
        context = {
            'اسم_الطالب': user_name,
            'المادة': subject_name
        }
        
        response = self._make_request(self.system_prompts['class_end_checkin'], context)
        if response:
            return response
        
        # Fallback message
        return "وصلت البيت؟ كلشي تمام؟ 🏠 إذا تحتاج شي قلي!"
    
    def generate_hydration_reminder(self, user_name: str, cups_today: int = 0) -> str:
        """Generate hydration reminder"""
        context = {
            'اسم_الطالب': user_name,
            'أكواب_اليوم': cups_today
        }
        
        response = self._make_request(self.system_prompts['hydration_reminder'], context)
        if response:
            return response
        
        # Fallback message
        return "يابه! شربت مي؟ 💧 الجسم يحتاج ماء عشان يشتغل زين!"
    
    def generate_evening_recap(self, user_data: Dict) -> str:
        """Generate comprehensive evening recap"""
        context = {
            'اسم_الطالب': user_data.get('name', 'صديقي'),
            'جلسات_الدراسة': user_data.get('study_sessions', []),
            'المواد_النشطة': user_data.get('active_subjects', []),
            'نشاطات_اليوم': user_data.get('daily_activities', []),
            'أكواب_الماء': user_data.get('water_cups', 0)
        }
        
        response = self._make_request(self.system_prompts['evening_recap'], context)
        if response:
            return response
        
        # Fallback message
        return """خلصنا يوم آخر! 📚
        
تلخيص اليوم: درست وتعبت، بس هاي بداية الطريق للنجاح.

مراجعة سريعة:
• راجع الملاحظات اللي كتبتها اليوم
• فكر بأهم 3 معلومات تعلمتها
• حضر نفسك لمحاضرة بكره

بكره خطة جديدة وإنجاز أكبر! 💪"""
    
    def generate_weekly_evaluation(self, user_stats: Dict) -> str:
        """Generate weekly performance evaluation"""
        context = {
            'احصائيات_الأسبوع': user_stats,
            'جلسات_الدراسة': user_stats.get('study_sessions', {}),
            'شرب_الماء': user_stats.get('water_intake', {}),
            'المواد': user_stats.get('subjects', [])
        }
        
        response = self._make_request(self.system_prompts['weekly_evaluation'], context)
        if response:
            return response
        
        # Fallback message
        return """تقييم الأسبوع 📊

نقاط القوة:
✅ الالتزام بجدول الدراسة
✅ التنوع في المواد
✅ الاهتمام بالصحة

يحتاج تحسين:
🔄 زيادة مدة جلسات الدراسة
🔄 شرب ماء أكثر
🔄 تنظيم وقت أفضل

الأسبوع الجديد هو فرصة للأفضل! 🚀"""
    
    def summarize_notes(self, notes_text: str, subject_name: str = None) -> str:
        """Summarize uploaded notes and generate flashcards"""
        context = {
            'المادة': subject_name,
            'نص_الملاحظات': notes_text[:2000]  # Limit context size
        }
        
        response = self._make_request(self.system_prompts['notes_summary'], context)
        if response:
            return response
        
        # Fallback message
        return f"""تم رفع الملاحظات! 📝

ملخص سريع:
• الملاحظات تحتوي معلومات مفيدة
• راجعها مرة ثانية خلال ساعة
• اعمل flashcards للنقاط المهمة

مهمة المراجعة: اقرأ الملاحظات واكتب 3 أسئلة عنها"""
    
    def generate_adaptive_response(self, user_message: str, context: Dict) -> str:
        """Generate contextually appropriate response"""
        full_context = {
            'رسالة_المستخدم': user_message,
            'معلومات_المستخدم': context.get('user_data', {}),
            'النشاط_الأخير': context.get('recent_activity', []),
            'الحالة_الحالية': context.get('current_state', {})
        }
        
        response = self._make_request(self.system_prompts['adaptive_response'], full_context)
        if response:
            return response
        
        # Fallback based on message keywords
        if any(word in user_message for word in ['رجعت', 'وصلت', 'البيت']):
            return "أهلين! استرح شوية وبعدين نكمل دراسة 📚"
        elif any(word in user_message for word in ['تعبان', 'متعب', 'مو قادر']):
            return "لا تشيل هم، استرح وارجع بقوة! الراحة مهمة للتركيز 💪"
        elif any(word in user_message for word in ['خلصت', 'انتهيت']):
            return "براڤو عليك! إنجاز رائع، يلا للمادة الثانية؟ 🎉"
        else:
            return "فهمت عليك! خبرني إذا تحتاج مساعدة بأي شي 😊"
    
    def generate_subject_plan(self, subject_name: str, current_level: str, goals: List[str] = None) -> str:
        """Generate study plan for specific subject"""
        context = {
            'المادة': subject_name,
            'المستوى_الحالي': current_level,
            'الأهداف': goals or []
        }
        
        prompt = """أنت RezeCoach. اعمل خطة دراسية للمادة المذكورة بالعامية العراقية.
                   الخطة يجب تحتوي على:
                   1. تقسيم المنهج لأجزاء
                   2. جدول زمني مقترح
                   3. طرق دراسة مناسبة
                   4. نصائح للحفظ والفهم
                   اجعل الخطة عملية وقابلة للتطبيق."""
        
        response = self._make_request(prompt, context)
        if response:
            return response
        
        return f"""خطة دراسة {subject_name} 📋

التقسيم:
• الأسبوع الأول: المفاهيم الأساسية
• الأسبوع الثاني: التطبيقات العملية  
• الأسبوع الثالث: حل المسائل
• الأسبوع الرابع: المراجعة الشاملة

نصائح:
- اقرأ قبل المحاضرة
- اعمل ملخصات بإيدك
- حل تمارين يومياً
- راجع كل 3 أيام

يلا نبدأ بقوة! 💪"""
    
    def analyze_study_pattern(self, sessions_data: List[Dict]) -> str:
        """Analyze study patterns and provide insights"""
        context = {
            'بيانات_الجلسات': sessions_data
        }
        
        prompt = """أنت RezeCoach. حلل نمط الدراسة للطالب وأعط تحليل بالعامية العراقية يحتوي على:
                   1. الأوقات المفضلة للدراسة
                   2. المواد اللي يركز عليها أكثر
                   3. مدة الجلسات المعتادة
                   4. اقتراحات للتحسين
                   اجعل التحليل مفيد وقابل للتطبيق."""
        
        response = self._make_request(prompt, context)
        if response:
            return response
        
        return """تحليل نمط الدراسة 📈

ملاحظات:
• تدرس أكثر في المساء
• تركز على المواد الرئيسية
• جلسات متوسطة المدة (30-60 دقيقة)

اقتراحات:
- جرب الدراسة الصباحية
- نوع في المواد خلال اليوم
- خذ استراحة كل 45 دقيقة

استمر على هذا المنوال! 👍"""
    
    def generate_motivation_message(self, user_name: str, achievement: str = None) -> str:
        """Generate motivational message"""
        context = {
            'اسم_الطالب': user_name,
            'الإنجاز': achievement
        }
        
        prompt = """أنت RezeCoach. اكتب رسالة تحفيزية بالعامية العراقية تشجع الطالب وتحفزه للاستمرار.
                   اجعل الرسالة إيجابية ومُلهمة وقصيرة."""
        
        response = self._make_request(prompt, context)
        if response:
            return response
        
        # Fallback motivational messages
        messages = [
            f"يا {user_name}، كل خطوة تخطوها تقربك من النجاح! 🌟",
            f"حلو والله {user_name}! كلش متقدم، استمر يمعود! 🎉",
            f"فخر فيك {user_name}! شغلك يخبل، خلي الكل يشوف قدراتك! 💪",
            f"ما شاء الله عليك {user_name}! هكذا يكون الإصرار! 🔥"
        ]
        
        import random
        return random.choice(messages)
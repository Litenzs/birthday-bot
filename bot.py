import asyncio
import json
import os
import datetime as dt
from datetime import datetime, date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import logging
from flask import Flask
import threading

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8927521831:AAGhXl9q9VJbvOqEoED3qMHPy5T0Vf0IZJ8"

WAITING_NAME, WAITING_DATE = range(2)

# Файлы для хранения данных
DATA_FILE = "birthdays.json"
NOTIFY_FILE = "notifications.json"

# Загрузка данных из файлов
def load_data():
    global birthdays, notification_users
    
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            birthdays = json.load(f)
    else:
        birthdays = {}
    
    if os.path.exists(NOTIFY_FILE):
        with open(NOTIFY_FILE, 'r', encoding='utf-8') as f:
            notification_users = set(json.load(f))
    else:
        notification_users = set()

# Сохранение данных в файлы
def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(birthdays, f, ensure_ascii=False, indent=2)
    
    with open(NOTIFY_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(notification_users), f)

# Загружаем данные при старте
load_data()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить день рождения", callback_data="add_birthday")],
        [InlineKeyboardButton("📋 Список дней рождений", callback_data="list_birthdays")],
        [InlineKeyboardButton("⏱ Детальный отсчет", callback_data="detailed_countdown")],
        [InlineKeyboardButton("📊 Ближайшие ДР", callback_data="upcoming")],
        [InlineKeyboardButton("🔔 Уведомления: ВКЛ" if user_id in notification_users else "🔕 Уведомления: ВЫКЛ", 
                             callback_data="toggle_notifications")]
    ])
    
    await update.message.reply_text(
        "🎂 Привет! Я бот для отслеживания дней рождений!\n\n"
        "📅 Показываю точное время до каждого ДР\n"
        "🔔 Могу присылать ежедневные уведомления\n"
        "💾 Все данные сохраняются!\n\n"
        "Выбери действие:",
        reply_markup=keyboard
    )

async def start_add_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✍️ Введи имя именинника:")
    return WAITING_NAME

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text("📅 Теперь введи дату рождения в формате ДД.ММ\nНапример: 18.07")
    return WAITING_DATE

async def receive_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        date_str = update.message.text
        day, month = map(int, date_str.split('.'))
        
        try:
            test_date = date(2024, month, day)
        except ValueError:
            await update.message.reply_text("❌ Некорректная дата! Попробуй еще раз.\nФормат: ДД.ММ")
            return WAITING_DATE
        
        name = context.user_data['name']
        user_id = str(update.effective_user.id)
        
        if user_id not in birthdays:
            birthdays[user_id] = []
        
        for bday in birthdays[user_id]:
            if bday['day'] == day and bday['month'] == month and bday['name'] == name:
                await update.message.reply_text(f"⚠️ День рождения {name} ({day:02d}.{month:02d}) уже добавлен!")
                return ConversationHandler.END
        
        birthdays[user_id].append({
            'name': name,
            'day': day,
            'month': month
        })
        
        birthdays[user_id].sort(key=lambda x: (x['month'], x['day']))
        save_data()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Добавить еще", callback_data="add_birthday")],
            [InlineKeyboardButton("🏠 В главное меню", callback_data="main_menu")]
        ])
        
        await update.message.reply_text(
            f"✅ День рождения {name} ({day:02d}.{month:02d}) успешно добавлен!",
            reply_markup=keyboard
        )
        
        return ConversationHandler.END
        
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Неверный формат! Введи дату как ДД.ММ\nНапример: 18.07")
        return WAITING_DATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Добавление отменено")
    return ConversationHandler.END

def get_time_until(day, month):
    now = datetime.now() + timedelta(hours=3)
    today = now.date()
    
    current_year_bday = datetime(now.year, month, day, 0, 0, 0)
    
    if current_year_bday.date() < today or (current_year_bday.date() == today and current_year_bday.time() <= now.time()):
        next_bday = datetime(now.year + 1, month, day, 0, 0, 0)
    else:
        next_bday = current_year_bday
    
    delta = next_bday - now
    
    total_seconds = int(delta.total_seconds())
    days = total_seconds // (24 * 3600)
    hours = (total_seconds % (24 * 3600)) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    
    return {
        'days': days,
        'hours': hours,
        'minutes': minutes,
        'seconds': seconds,
        'total_seconds': total_seconds,
        'date': next_bday,
        'is_today': days == 0 and next_bday.date() == today
    }

async def list_birthdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    
    if user_id not in birthdays or not birthdays[user_id]:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Добавить ДР", callback_data="add_birthday")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ])
        await query.edit_message_text("📭 У тебя пока нет добавленных дней рождений!", reply_markup=keyboard)
        return
    
    text = "🎂 Твои дни рождения:\n\n"
    
    for bday in birthdays[user_id]:
        time_data = get_time_until(bday['day'], bday['month'])
        date_str = f"{bday['day']:02d}.{bday['month']:02d}"
        
        if time_data['is_today']:
            status = "🎉 СЕГОДНЯ!"
        elif time_data['days'] == 0:
            status = "🎊 ЗАВТРА!"
        elif time_data['days'] <= 7:
            status = f"🔥 через {time_data['days']} дн. {time_data['hours']} ч."
        else:
            status = f"📆 через {time_data['days']} дн."
        
        text += f"{bday['name']} — {date_str}\n└ {status}\n\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏱ Детальный отсчет", callback_data="detailed_countdown")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="list_birthdays")],
        [InlineKeyboardButton("❌ Удалить ДР", callback_data="delete_birthday")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard)

async def detailed_countdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    
    if user_id not in birthdays or not birthdays[user_id]:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Добавить ДР", callback_data="add_birthday")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ])
        await query.edit_message_text("📭 Нет добавленных дней рождений!", reply_markup=keyboard)
        return
    
    sorted_bdays = sorted(birthdays[user_id], key=lambda x: get_time_until(x['day'], x['month'])['total_seconds'])
    
    text = "⏱ Детальный отсчет:\n\n"
    
    for bday in sorted_bdays[:5]:
        time_data = get_time_until(bday['day'], bday['month'])
        date_str = f"{bday['day']:02d}.{bday['month']:02d}"
        
        if time_data['is_today']:
            text += f"🎉 {bday['name']} — {date_str}\n🎂 СЕГОДНЯ!\n\n"
        else:
            text += (
                f"📅 {bday['name']} — {date_str}\n"
                f"├ 📆 Дней: {time_data['days']}\n"
                f"├ 🕐 Часов: {time_data['hours']}\n"
                f"├ ⏱ Минут: {time_data['minutes']}\n"
                f"└ ⏲ Секунд: {time_data['seconds']}\n\n"
            )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Обновить", callback_data="detailed_countdown")],
        [InlineKeyboardButton("📋 Список ДР", callback_data="list_birthdays")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard)

async def show_upcoming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    
    if user_id not in birthdays or not birthdays[user_id]:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Добавить ДР", callback_data="add_birthday")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ])
        await query.edit_message_text("📭 Нет добавленных дней рождений!", reply_markup=keyboard)
        return
    
    sorted_bdays = sorted(birthdays[user_id], key=lambda x: get_time_until(x['day'], x['month'])['total_seconds'])
    
    text = "📊 Ближайшие дни рождения:\n\n"
    
    for bday in sorted_bdays[:5]:
        time_data = get_time_until(bday['day'], bday['month'])
        date_str = f"{bday['day']:02d}.{bday['month']:02d}"
        
        if time_data['is_today']:
            text += f"🎉 {bday['name']} — СЕГОДНЯ!\n"
        elif time_data['days'] == 0:
            text += f"⭐ {bday['name']} — завтра ({date_str})\n"
        else:
            text += f"📅 {bday['name']} — через {time_data['days']} дн. {time_data['hours']} ч. ({date_str})\n"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏱ Детальный отсчет", callback_data="detailed_countdown")],
        [InlineKeyboardButton("🔄 Обновить", callback_data="upcoming")],
        [InlineKeyboardButton("📋 Все ДР", callback_data="list_birthdays")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await query.edit_message_text(text, reply_markup=keyboard)

async def toggle_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if user_id in notification_users:
        notification_users.remove(user_id)
        status = "🔕 Уведомления выключены"
    else:
        notification_users.add(user_id)
        status = "🔔 Уведомления включены!\nБот будет присылать отсчет каждый день в 10:00 МСК"
    
    save_data()
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить день рождения", callback_data="add_birthday")],
        [InlineKeyboardButton("📋 Список дней рождений", callback_data="list_birthdays")],
        [InlineKeyboardButton("⏱ Детальный отсчет", callback_data="detailed_countdown")],
        [InlineKeyboardButton("📊 Ближайшие ДР", callback_data="upcoming")],
        [InlineKeyboardButton("🔔 Уведомления: ВКЛ" if user_id in notification_users else "🔕 Уведомления: ВЫКЛ", 
                             callback_data="toggle_notifications")]
    ])
    
    await query.edit_message_text(f"🎂 Главное меню\n\n{status}\n\nВыбери действие:", reply_markup=keyboard)

async def delete_birthday_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    
    if user_id not in birthdays or not birthdays[user_id]:
        await query.edit_message_text("📭 Нечего удалять!")
        return
    
    keyboard = []
    for i, bday in enumerate(birthdays[user_id]):
        date_str = f"{bday['day']:02d}.{bday['month']:02d}"
        keyboard.append([InlineKeyboardButton(f"❌ {bday['name']} ({date_str})", callback_data=f"delete_{i}")])
    
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
    
    await query.edit_message_text("🗑 Выбери день рождения для удаления:", reply_markup=InlineKeyboardMarkup(keyboard))

async def delete_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(update.effective_user.id)
    index = int(query.data.split('_')[1])
    
    if 0 <= index < len(birthdays[user_id]):
        removed = birthdays[user_id].pop(index)
        save_data()
        await query.edit_message_text(f"✅ День рождения {removed['name']} удален!\n\nНажми /start для возврата в меню")

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить день рождения", callback_data="add_birthday")],
        [InlineKeyboardButton("📋 Список дней рождений", callback_data="list_birthdays")],
        [InlineKeyboardButton("⏱ Детальный отсчет", callback_data="detailed_countdown")],
        [InlineKeyboardButton("📊 Ближайшие ДР", callback_data="upcoming")],
        [InlineKeyboardButton("🔔 Уведомления: ВКЛ" if user_id in notification_users else "🔕 Уведомления: ВЫКЛ", 
                             callback_data="toggle_notifications")]
    ])
    
    await query.edit_message_text("🎂 Главное меню\n\nВыбери действие:", reply_markup=keyboard)

async def send_daily_notifications(context):
    current_time = datetime.now() + timedelta(hours=3)
    logger.info(f"Запуск ежедневных уведомлений в {current_time}")
    
    load_data()
    
    for user_id in notification_users:
        try:
            if str(user_id) in birthdays and birthdays[str(user_id)]:
                sorted_bdays = sorted(birthdays[str(user_id)], key=lambda x: get_time_until(x['day'], x['month'])['total_seconds'])
                
                text = f"🔔 Ежедневный отсчет! ({current_time.strftime('%d.%m.%Y')})\n\n"
                
                for bday in sorted_bdays[:3]:
                    time_data = get_time_until(bday['day'], bday['month'])
                    date_str = f"{bday['day']:02d}.{bday['month']:02d}"
                    
                    if time_data['is_today']:
                        text += f"🎉 {bday['name']} — СЕГОДНЯ!\n\n"
                    else:
                        text += f"📅 {bday['name']} — {date_str}\n└ ⏳ Осталось: {time_data['days']} дн. {time_data['hours']} ч. {time_data['minutes']} мин. {time_data['seconds']} сек.\n\n"
                
                text += "💡 Используй /start для управления днями рождения!"
                
                await context.bot.send_message(chat_id=user_id, text=text)
                logger.info(f"Уведомление отправлено пользователю {user_id}")
        except Exception as e:
            logger.error(f"Ошибка: {e}")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_birthday, pattern="add_birthday")],
        states={
            WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
            WAITING_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(list_birthdays, pattern="list_birthdays"))
    application.add_handler(CallbackQueryHandler(detailed_countdown, pattern="detailed_countdown"))
    application.add_handler(CallbackQueryHandler(show_upcoming, pattern="upcoming"))
    application.add_handler(CallbackQueryHandler(toggle_notifications, pattern="toggle_notifications"))
    application.add_handler(CallbackQueryHandler(delete_birthday_menu, pattern="delete_birthday"))
    application.add_handler(CallbackQueryHandler(delete_birthday, pattern=r"delete_\d+"))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="main_menu"))
    
    if application.job_queue:
        # Раз в день в 7:00 UTC = 10:00 МСК
        application.job_queue.run_daily(send_daily_notifications, time=dt.time(hour=7, minute=0))
        logger.info("🔔 Уведомления настроены на 10:00 МСК каждый день")
    
    app = Flask(__name__)
    
    @app.route('/')
    def home():
        return "Bot is running!"
    
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=10000), daemon=True).start()
    
    logger.info("🤖 Бот запущен!")
    print("🤖 Бот запущен! Уведомления в 10:00 МСК")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

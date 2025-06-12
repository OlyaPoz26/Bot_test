import logging
import datetime
import gspread
from typing import Union
from telegram import CallbackQuery
from oauth2client.service_account import ServiceAccountCredentials
from telegram import ReplyKeyboardMarkup, Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ConversationHandler, ContextTypes, CallbackQueryHandler
)
from dotenv import load_dotenv
import os

load_dotenv()  # Загружает переменные из .env

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SPREADSHEET_KEY = os.getenv("GOOGLE_SHEETS_KEY")

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Этапы
(MENU, CATEGORY, DESCRIPTION, AMOUNT, WHO, INCOME_TYPE, INCOME_WHO, INCOME_AMOUNT,
 ORDER_ITEM, ORDER_QUANTITY, ORDER_PRICE, ORDER_DATE,
 PAYMENT_ACTION, CHANGE_STATUS, ORDER_CUSTOMER) = range(15)

# Подключение к Google Таблице
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("telegram-expense-bot.json", scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(SPREADSHEET_KEY)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Расходы", "Доходы", "Заказы"], ["Оплата"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Выберите категорию:", reply_markup=reply_markup)
    return MENU

def get_status_keyboard():
    """Создает клавиатуру с цветными кнопками статусов"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟦 План", callback_data="status_План"),
            InlineKeyboardButton("🟩 Факт", callback_data="status_Факт")
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_status_change")]
    ])


# Обработчик меню
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data['mode'] = text

    if text == "Расходы":
        await update.message.reply_text("Введите категорию расхода:")
        return CATEGORY
    elif text == "Доходы":
        await update.message.reply_text("Введите тип дохода:")
        return INCOME_TYPE
    elif text == "Заказы":
        await update.message.reply_text("Кто заказал:")
        return ORDER_CUSTOMER
    elif text == "Оплата":
        return await show_recent_orders(update, context)
    else:
        await update.message.reply_text("Пожалуйста, выберите кнопку.")
        return MENU

# ======= Расходы ======= 
async def category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["category"] = update.message.text
    await update.message.reply_text("На что потрачено?")
    return DESCRIPTION

async def description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["description"] = update.message.text
    await update.message.reply_text("Введите сумму:")
    return AMOUNT

async def amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["amount"] = update.message.text
    await update.message.reply_text("Кто потратил?")
    return WHO

async def who(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["who"] = update.message.text
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")

    row = [
        context.user_data["category"],
        context.user_data["description"],
        context.user_data["amount"],
        context.user_data["who"],
        now,
    ]
    worksheet = spreadsheet.worksheet("CF_out_bot")
    worksheet.append_row(row)
    await update.message.reply_text("✅ Расход записан! Напиши /start для нового ввода.")
    return ConversationHandler.END

# ======= Доходы =======
async def income_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["income_type"] = update.message.text
    await update.message.reply_text("Кто оплатил?")
    return INCOME_WHO

async def income_who(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["income_who"] = update.message.text
    await update.message.reply_text("Введите сумму дохода:")
    return INCOME_AMOUNT

async def income_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    worksheet = spreadsheet.worksheet("CF_in_bot")
    worksheet.append_row([
        now,
        context.user_data["income_type"],
        context.user_data["income_who"],
        update.message.text
    ])
    await update.message.reply_text("✅ Доход записан! Напиши /start для нового ввода.")
    return ConversationHandler.END

# ======= Заказы =======

# Отмена
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено.")
    return ConversationHandler.END

# ======= Заказы =======
async def order_customer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["customer"] = update.message.text
    await update.message.reply_text("Введите название товара:")
    return ORDER_ITEM

async def order_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["item"] = update.message.text
    await update.message.reply_text("Введите количество (в кг):")
    return ORDER_QUANTITY

async def order_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["quantity"] = update.message.text
    await update.message.reply_text("Введите цену:")
    return ORDER_PRICE

async def order_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Получаем цену и количество, преобразуем в числа
        price = float(update.message.text.replace(',', '.'))
        quantity = float(context.user_data["quantity"].replace(',', '.'))
        
        # Сохраняем цену и рассчитываем сумму
        context.user_data["price"] = price
        context.user_data["order_amount"] = round(price * quantity, 2)
        
        await update.message.reply_text(
            f"Сумма: {context.user_data['order_amount']} ₸ (рассчитано автоматически)\n"
            "Введите дату доставки (ДД.ММ.ГГГГ):"
        )
        return ORDER_DATE
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число! Например: 150 или 99.50")
        return ORDER_PRICE

async def order_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["delivery_date"] = update.message.text
    context.user_data["status"] = "План"  # Автоматически устанавливаем статус
    
    now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    
    try:
        worksheet = spreadsheet.worksheet("CF_orders_bot")
        worksheet.append_row([
            context.user_data["item"],
            context.user_data["quantity"],
            context.user_data["price"],
            context.user_data["order_amount"],
            context.user_data["delivery_date"],
            now,
            context.user_data["status"],
            context.user_data["customer"]  # Используем "План" по умолчанию
        ])
        
        # Получаем номер последней строки и применяем стиль
        all_values = worksheet.get_all_values()
        last_row = len(all_values)
        set_status_style(worksheet, last_row, "План")
        
        await update.message.reply_text("✅ Заказ записан (статус: План)! Напиши /start для нового ввода.")
    except Exception as e:
        logger.error(f"Ошибка при сохранении заказа: {e}")
        await update.message.reply_text("❌ Не удалось сохранить заказ.")
    
    return ConversationHandler.END

# ======= Оплата =======
async def show_recent_orders(update: Union[Update, CallbackQuery], context: ContextTypes.DEFAULT_TYPE):
    # Определяем, откуда пришел update
    if isinstance(update, CallbackQuery):
        message = update.message
    else:
        message = update.message
    
    worksheet = spreadsheet.worksheet("CF_orders_bot")
    records = worksheet.get_all_records()
    
    one_week_ago = datetime.datetime.now() - datetime.timedelta(days=7)
    recent_orders = []
    
    for idx, record in enumerate(records, start=2):
        try:
            record_date = datetime.datetime.strptime(record['Дата добавления'], "%d.%m.%Y %H:%M")
            if record_date >= one_week_ago:
                recent_orders.append((idx, record))
        except:
            continue
    
    if not recent_orders:
        await message.reply_text("Нет заказов за последнюю неделю.")
        return MENU
    
    context.user_data['recent_orders'] = recent_orders
    
    msg = "Последние заказы (неделя):\n\n"
    for idx, (row_num, order) in enumerate(recent_orders, start=1):
        msg += (f"{idx}. {order['Товар']} - {order['Количество']}кг - "
               f"{order['Цена']}₸ - Статус: {order.get('Статус', 'не указан')}\n")
    
    # Создаем кнопки для изменения статуса + кнопку отмены
    keyboard = [
        [InlineKeyboardButton(f"Изменить статус {i+1}", callback_data=f"change_{row_num}")] 
        for i, (row_num, _) in enumerate(recent_orders)
    ]
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_payment")])  # Новая кнопка
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if isinstance(update, CallbackQuery):
        await message.edit_text(msg, reply_markup=reply_markup)
    else:
        await message.reply_text(msg, reply_markup=reply_markup)
    
    return PAYMENT_ACTION

async def payment_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_payment":
        await query.edit_message_text("❌ Действие отменено. Напиши /start для нового ввода.")
        return ConversationHandler.END
    elif query.data.startswith("change_"):
        row_num = int(query.data.split("_")[1])
        context.user_data['editing_row'] = row_num
        
        # Используем ту же цветную клавиатуру
        await query.edit_message_text(
            text="Выберите новый статус:",
            reply_markup=get_status_keyboard()
        )
        return CHANGE_STATUS


def set_status_style(worksheet, row, status):
    """Устанавливает цвет фона в зависимости от статуса"""
    format_dict = {
        "План": {
            "backgroundColor": {"red": 0.0, "green": 0.5, "blue": 1.0},  # Светло-синий
            "textFormat": {"bold": True}
        },
        "Факт": {
            "backgroundColor": {"red": 0.0, "green": 1.0, "blue": 0.2},  # Светло-зеленый
            "textFormat": {"bold": True}
        }
    }
    
    # Форматируем ячейку статуса (колонка G)
    worksheet.format(f"G{row}", format_dict.get(status, {}))

async def change_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_status_change":
        await query.edit_message_text("❌ Изменение статуса отменено.")
        return await show_recent_orders(query, context)
    
    new_status = query.data.split("_")[1]
    row_num = context.user_data['editing_row']
    
    try:
        worksheet = spreadsheet.worksheet("CF_orders_bot")
        worksheet.update_cell(row_num, 7, new_status)
        set_status_style(worksheet, row_num, new_status)
        await query.edit_message_text(f"✅ Статус изменен на '{new_status}'!")
        return await show_recent_orders(query, context)
    except Exception as e:
        logger.error(f"Ошибка при изменении статуса: {e}")
        await query.edit_message_text("❌ Не удалось изменить статус.")
        return ConversationHandler.END

# Отмена
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено.")
    return ConversationHandler.END

# Запуск бота
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler)],
            
            CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, category)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, amount)],
            WHO: [MessageHandler(filters.TEXT & ~filters.COMMAND, who)],
            
            INCOME_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, income_type)],
            INCOME_WHO: [MessageHandler(filters.TEXT & ~filters.COMMAND, income_who)],
            INCOME_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, income_amount)],
            
            ORDER_CUSTOMER: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_customer)],
            ORDER_ITEM: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_item)],
            ORDER_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_quantity)],
            ORDER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_price)],
            ORDER_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_date)],
            PAYMENT_ACTION: [CallbackQueryHandler(payment_action)],
            CHANGE_STATUS:  [
            CallbackQueryHandler(change_status, pattern="^status_"),
            CallbackQueryHandler(change_status, pattern="^cancel_status_change$")
        ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
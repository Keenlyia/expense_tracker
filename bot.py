import asyncio
import aiohttp
import os
import re
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv
from datetime import datetime
from io import BytesIO

# Завантажуємо змінні з .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Ініціалізація бота та диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# URL API FastAPI
API_URL_ADD_EXPENSE = "http://127.0.0.1:8001/add_expense/"
API_URL_GET_EXPENSES = "http://127.0.0.1:8001/get_expenses/"
API_URL_DELETE_EXPENSE = "http://127.0.0.1:8001/delete_expense/"
API_URL_GET_EXPENSES_REPORT = "http://127.0.0.1:8001/get_expenses_report/?start_date={}&end_date={}"
API_URL_EDIT_EXPENSE = "http://localhost:8001/edit_expense/"

# Стани для введення витрати
class ExpenseForm(StatesGroup):
    select_id = State()
    name = State()
    date = State()
    amount = State()

class ExpenseDelete(StatesGroup):
    select_id = State()

class ReportForm(StatesGroup):
    start_date = State()
    end_date = State()

# Стани для редагування витрати
class EditExpenseForm(StatesGroup):
    select_id = State()
    name = State()
    date = State()
    amount = State()


# Обробник команди /start
@dp.message(Command("start"))
async def start_command(message: Message):
    await message.answer("Я бот для контролю витрат. Використовуйте команди:\n"
                         "/add_expense - додати витрату\n"
                         "/get_expenses - переглянути витрати за датою\n"
                         "/delete_expense - видалити статтю з витратами за id\n"
                         "/edit_expense - редагувати статтю з витратами"
                         )


# Обробник команди /add_expense
@dp.message(Command("add_expense"))
async def add_expense_start(message: Message, state: FSMContext):
    await state.set_state(ExpenseForm.name)
    await message.answer("Введіть назву витрати:")


# Отримуємо назву витрати
@dp.message(ExpenseForm.name)
async def add_expense_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(ExpenseForm.date)
    await message.answer("Тепер введіть дату (у форматі dd.mm.yyyy):")


# Отримуємо дату
@dp.message(ExpenseForm.date)
async def add_expense_date(message: Message, state: FSMContext):
    date = message.text.strip()
    # Перевірка формату дати (dd.mm.yyyy)
    date_pattern = r"\d{2}\.\d{2}\.\d{4}"
    if not re.match(date_pattern, date):
        await message.answer("❌ Невірний формат дати. Використовуйте формат dd.mm.yyyy.")
        return
    await state.update_data(date=date)
    await state.set_state(ExpenseForm.amount)
    await message.answer("Введіть суму витрати у гривнях:")


# Отримуємо суму та відправляємо до API
@dp.message(ExpenseForm.amount)
async def add_expense_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
    except ValueError:
        await message.answer("❌ Введіть коректне число для суми.")
        return

    data = await state.get_data()
    expense_data = {
        "name": data["name"],
        "date": data["date"],
        "amount": amount
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(API_URL_ADD_EXPENSE, json=expense_data) as response:
            if response.status == 200:
                await message.answer("✅ Витрату успішно додано!")
            else:
                await message.answer("❌ Сталася помилка, спробуйте ще раз.")

    await state.clear()

# Обробник команди /get_expenses
@dp.message(Command("get_expenses"))
async def ask_for_dates(message: types.Message, state: FSMContext):
    await state.set_state(ReportForm.start_date)  # Створюємо стан для введення дат
    await message.answer("Введіть діапазон дат у форматі: ДД.ММ.РРРР-ДД.ММ.РРРР")

# Обробник введення діапазону дат для звіту
@dp.message(ReportForm.start_date)
async def send_report(message: types.Message, state: FSMContext):
    try:
        start_date, end_date = message.text.split("-")
        # Перевіряємо формат дат
        date_pattern = r"\d{2}\.\d{2}\.\d{4}"
        if not re.match(date_pattern, start_date.strip()) or not re.match(date_pattern, end_date.strip()):
            await message.answer("❌ Неправильний формат дат. Введіть у форматі ДД.ММ.РРРР-ДД.ММ.РРРР")
            return

        file_path = "expenses_report.xlsx"
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL_GET_EXPENSES_REPORT.format(start_date.strip(), end_date.strip())) as resp:
                if resp.status == 200:
                    with open(file_path, "wb") as f:
                        f.write(await resp.read())
                    await message.answer_document(FSInputFile(file_path))
                else:
                    await message.answer(f"Помилка отримання звіту: {resp.status}")

        # Очищаємо стан після завершення обробки
        await state.clear()

    except ValueError:
        await message.answer("❌ Неправильний формат. Введіть у форматі ДД.ММ.РРРР-ДД.ММ.РРРР")


@dp.message(Command("delete_expense"))
async def delete_expense_start(message: Message, state: FSMContext):
    await state.set_state(ExpenseDelete.select_id)
    await message.answer("Введіть ID витрати, яку потрібно видалити:")

# Обробник введеного ID та видалення витрати
@dp.message(ExpenseDelete.select_id)
async def delete_expense_confirm(message: Message, state: FSMContext):
    expense_id = message.text.strip()

    if not expense_id.isdigit():
        await message.answer("❌ Введіть коректний числовий ID витрати.")
        return

    async with aiohttp.ClientSession() as session:
        try:
            delete_url = f"{API_URL_DELETE_EXPENSE}{expense_id}/"
            async with session.delete(delete_url) as response:
                if response.status == 200:
                    response_data = await response.json()
                    await message.answer(f"✅ {response_data['message']}")
                elif response.status == 404:
                    await message.answer("❌ Витрату з таким ID не знайдено.")
                else:
                    await message.answer("❌ Помилка при видаленні витрати. Спробуйте ще раз.")
        except Exception as e:
            await message.answer(f"❌ Помилка при з'єднанні з API: {str(e)}")

    await state.clear()
    await start_command(message)

# Команда /edit_expense
@dp.message(Command("edit_expense"))
async def edit_expense_start(message: Message, state: FSMContext):
    await message.answer("Введіть ID витрати для редагування:")
    await state.set_state(EditExpenseForm.select_id)

# Обробник введення ID для редагування
@dp.message(EditExpenseForm.select_id)
async def process_edit_expense_id(message: Message, state: FSMContext):
    expense_id = message.text.strip()
    if not expense_id.isdigit():
        await message.answer("❌ Введіть коректний ID витрати.")
        return
    await state.update_data(expense_id=expense_id)
    await message.answer("Введіть нову назву витрати:")
    await state.set_state(EditExpenseForm.name)

# Обробник введення нової назви витрати
@dp.message(EditExpenseForm.name)
async def process_edit_expense_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("❌ Назва витрати не може бути порожньою.")
        return
    await state.update_data(name=name)
    await message.answer("Введіть нову дату витрати (формат dd.mm.yyyy):")
    await state.set_state(EditExpenseForm.date)

# Обробник введення нової дати витрати
@dp.message(EditExpenseForm.date)
async def process_edit_expense_date(message: Message, state: FSMContext):
    date = message.text.strip()
    date_pattern = r"\d{2}\.\d{2}\.\d{4}"
    if not re.match(date_pattern, date):
        await message.answer("❌ Невірний формат дати. Використовуйте формат dd.mm.yyyy.")
        return
    await state.update_data(date=date)
    await message.answer("Введіть нову суму витрати у гривнях:")
    await state.set_state(EditExpenseForm.amount)

# Обробник введення нової суми витрати
@dp.message(EditExpenseForm.amount)
async def process_edit_expense_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
    except ValueError:
        await message.answer("❌ Введіть коректну суму витрати.")
        return

    data = await state.get_data()
    expense_id = data["expense_id"]
    updated_expense = {
        "name": data["name"],
        "date": data["date"],
        "amount": amount
    }

    async with aiohttp.ClientSession() as session:
        update_url = f"{API_URL_EDIT_EXPENSE}{expense_id}/"
        async with session.put(update_url, json=updated_expense) as response:
            if response.status == 200:
                expense = await response.json()
                await message.answer(f"✅ Витрату оновлено:\n"
                                     f"ID: {expense['id']}\n"
                                     f"Назва: {expense['name']}\n"
                                     f"Дата: {expense['date']}\n"
                                     f"Сума: {expense['amount']} грн.")
            else:
                await message.answer("❌ Помилка при оновленні витрати. Спробуйте ще раз.")

    await state.clear()



# Запускаємо бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot off")

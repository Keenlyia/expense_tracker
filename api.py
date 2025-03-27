import openpyxl
import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, Column, Integer, String, Float, Date
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from pydantic import BaseModel
import datetime
from io import BytesIO
from fastapi.responses import StreamingResponse
from fastapi.responses import Response

# Налаштування бази даних SQLite
DATABASE_URL = "sqlite:///./expenses.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False, "timeout": 10})  # Додавання timeout
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Модель SQLAlchemy
class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    date = Column(Date, default=datetime.date.today)
    amount = Column(Float)

# Створюємо таблиці
Base.metadata.create_all(bind=engine)

# Pydantic-схема для API-запитів
class ExpenseCreate(BaseModel):
    name: str
    date: str
    amount: float

# Ініціалізація FastAPI
app = FastAPI()

# Отримання сесії БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Додавання витрати
@app.post("/add_expense/")
async def add_expense(expense: ExpenseCreate, db: Session = Depends(get_db)):
    try:
        expense_date = datetime.datetime.strptime(expense.date, "%d.%m.%Y").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Неправильний формат дати (використовуйте dd.mm.YYYY)")

    new_expense = Expense(name=expense.name, date=expense_date, amount=expense.amount)
    db.add(new_expense)
    db.commit()
    db.refresh(new_expense)

    return {"message": "Витрату додано успішно", "expense": {
        "id": new_expense.id,
        "name": new_expense.name,
        "date": new_expense.date.strftime("%d.%m.%Y"),
        "amount": new_expense.amount
    }}

@app.get("/get_all_expenses/")
async def get_expenses(db: Session = Depends(get_db)):
    expenses = db.query(Expense).all()
    if not expenses:
        raise HTTPException(status_code=404, detail="Витрати не знайдені")

    return expenses

@app.get("/get_expenses_report/")
async def get_expenses_report(start_date: str, end_date: str, db: Session = Depends(get_db)):
    try:
        start_date_obj = datetime.datetime.strptime(start_date, "%d.%m.%Y").date()
        end_date_obj = datetime.datetime.strptime(end_date, "%d.%m.%Y").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Неправильний формат дати (використовуйте dd.mm.YYYY)")

    expenses = db.query(Expense).filter(Expense.date >= start_date_obj, Expense.date <= end_date_obj).all()

    if not expenses:
        raise HTTPException(status_code=404, detail="Витрат за вказаний період не знайдено")

    # Створення Excel-файлу за допомогою openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Expenses Report"

    # Створення заголовків
    ws.append(["ID", "Name", "Date", "Amount"])

    # Додавання даних витрат
    for exp in expenses:
        ws.append([exp.id, exp.name, exp.date.strftime("%d.%m.%Y"), exp.amount])

    # Загальна сума витрат
    total_amount = sum(exp.amount for exp in expenses)
    ws.append(["", "", "Total", total_amount])

    # Створення буфера для збереження файлу в пам'яті
    excel_file = BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)
    file_data = excel_file.getvalue()

    return Response(content=file_data,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=expenses_report.xlsx"})


@app.delete("/delete_expense/{expense_id}")
async def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    try:
        expense = db.query(Expense).filter(Expense.id == expense_id).first()

        if not expense:
            raise HTTPException(status_code=404, detail="Витрату не знайдено")

        db.delete(expense)
        db.commit()  # Фіксуємо зміни
    except Exception as e:
        db.rollback()  # Якщо сталася помилка, скасовуємо зміни
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()  # Закриваємо сесію
    return {"message": f"Витрату з ID {expense_id} успішно видалено"}


@app.put("/edit_expense/{expense_id}")
async def edit_expense(expense_id: int, expense: ExpenseCreate, db: Session = Depends(get_db)):
    try:
        # Перевіряємо, чи існує витрата з таким ID
        db_expense = db.query(Expense).filter(Expense.id == expense_id).first()

        if not db_expense:
            raise HTTPException(status_code=404, detail="Витрату не знайдено")

        # Перетворюємо дату на формат datetime
        try:
            expense_date = datetime.datetime.strptime(expense.date, "%d.%m.%Y").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Неправильний формат дати (використовуйте dd.mm.YYYY)")

        # Оновлюємо витрату
        db_expense.name = expense.name
        db_expense.date = expense_date
        db_expense.amount = expense.amount

        db.commit()
        db.refresh(db_expense)

        return {"message": "Витрату успішно оновлено", "expense": {
            "id": db_expense.id,
            "name": db_expense.name,
            "date": db_expense.date.strftime("%d.%m.%Y"),
            "amount": db_expense.amount
        }}

    except Exception as e:
        db.rollback()  # Якщо сталася помилка, скасовуємо зміни
        raise HTTPException(status_code=500, detail=str(e))

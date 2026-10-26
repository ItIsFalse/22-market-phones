from app import create_app
from app.extensions import db
from app.models import Phone, PhonePurchase, Sale, CashAccount, Currency
from app.services.cash import apply_transaction
from datetime import datetime
from decimal import Decimal

app = create_app()

with app.app_context():
    print("Добавляем тестовые простые продажи...")

    # Получаем дефолтную USD-кассу
    account = CashAccount.query.filter_by(currency=Currency.USD).first()
    if not account:
        print("Ошибка: Нет USD-кассы!")
        exit()

    # Данные для телефонов
    phones_data = [
        {"brand": "Apple", "model": "iPhone 14", "imei": "999111222", "purchase_price": 500, "sale_price": 650, "sale_date": datetime(2026, 7, 15)}, # Лето
        {"brand": "Samsung", "model": "Galaxy S23", "imei": "999333444", "purchase_price": 400, "sale_price": 550, "sale_date": datetime(2026, 8, 20)}, # Лето
        {"brand": "Xiaomi", "model": "13T", "imei": "999555666", "purchase_price": 300, "sale_price": 450, "sale_date": datetime.utcnow()}, # Сегодня (Осень)
    ]

    for p_data in phones_data:
        # Проверяем, нет ли уже такого IMEI
        existing = PhonePurchase.query.filter_by(imei=p_data["imei"]).first()
        if existing:
            print(f"Телефон {p_data['brand']} {p_data['model']} уже есть в базе. Пропускаем.")
            continue

        # 1. Создаём закупку (историческая)
        purchase = PhonePurchase(
            brand=p_data["brand"], model=p_data["model"], imei=p_data["imei"],
            price=Decimal(str(p_data["purchase_price"])), currency=Currency.USD,
            cash_account_id=account.id,
            created_at=p_data["sale_date"] # Закупили в тот же день для простоты
        )
        db.session.add(purchase)
        db.session.flush()

        phone = Phone(purchase_id=purchase.id, status="sold") # Сразу продан
        db.session.add(phone)
        db.session.flush()

        # Транзакция закупки (расход)
        apply_transaction(
            account=account, type_="expense", amount=purchase.price,
            description=f"Закупка: {purchase.brand} {purchase.model}",
            source_type="purchase", source_id=purchase.id
        )

        # 2. Создаём продажу
        sale = Sale(
            phone_id=phone.id,
            client_name=f"Клиент {p_data['brand']}",
            client_contact="+998 90 000 00 00",
            price=Decimal(str(p_data["sale_price"])), currency=Currency.USD,
            cash_account_id=account.id,
            sold_at=p_data["sale_date"]
        )
        db.session.add(sale)
        db.session.flush()

        # Транзакция продажи (доход)
        apply_transaction(
            account=account, type_="income", amount=sale.price,
            description=f"Продажа: {phone.brand} {phone.model}",
            source_type="sale", source_id=sale.id
        )

    db.session.commit()
    print("Готово! Добавлено 3 простые продажи (2 летом, 1 сегодня).")
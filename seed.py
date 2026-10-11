"""
Разовый скрипт: наполняет базу тестовыми данными.
Запуск:  python seed.py
Повторный запуск ничего не дублирует.
"""
from datetime import datetime, timedelta
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models import (
    CashAccount, Currency,
    PhonePurchase, Phone,
    Sale,
    Customer,
    Installment, InstallmentPayment,
    Debtor, DebtorTransaction,
)
from app.services.cash import create_account, apply_transaction


def get_or_create_account(name, currency, initial_balance=0):
    """Возвращает существующий счёт по имени или создаёт новый."""
    account = CashAccount.query.filter_by(name=name).first()
    if account:
        return account
    return create_account(name=name, currency=currency, initial_balance=initial_balance)


def seed():
    app = create_app()
    with app.app_context():
        if PhonePurchase.query.count() > 0:
            print("В базе уже есть данные — пропускаю.")
            return

        # ===== 1. Кассы =====
        cash_usd = get_or_create_account("Сейф USD", Currency.USD, initial_balance=5_000)
        cash_uzs = get_or_create_account("Сейф UZS", Currency.UZS, initial_balance=50_000_000)
        card_uzs = get_or_create_account("Карта UZS", Currency.UZS, initial_balance=10_000_000)
        card_usd = get_or_create_account("Карта USD", Currency.USD, initial_balance=2_000)

        # ===== 2. Закупки =====
        purchases_data = [
            {"brand": "Apple", "model": "iPhone 13", "color": "Чёрный", "storage": "128",
             "battery": "3200 mAh", "imei": "111111111111111", "has_box": True,
             "price": Decimal("500"), "currency": Currency.USD,
             "account": cash_usd, "client_name": "Алишер", "client_contact": "+998901112233"},
            {"brand": "Apple", "model": "iPhone 14 Pro", "color": "Синий", "storage": "256",
             "battery": "3200 mAh", "imei": "222222222222222", "has_box": True,
             "price": Decimal("900"), "currency": Currency.USD,
             "account": cash_usd, "client_name": "Бекзод", "client_contact": "+998902223344"},
            {"brand": "Samsung", "model": "Galaxy S22", "color": "Белый", "storage": "128",
             "battery": "3700 mAh", "imei": "333333333333333", "has_box": True,
             "price": Decimal("400"), "currency": Currency.USD,
             "account": cash_usd, "client_name": "Дилшод", "client_contact": "+998903334455"},
            {"brand": "Xiaomi", "model": "Redmi Note 12", "color": "Серый", "storage": "64",
             "battery": "5000 mAh", "imei": "444444444444444", "has_box": False,
             "price": Decimal("150"), "currency": Currency.USD,
             "account": cash_usd, "client_name": "Шохрух", "client_contact": "+998904445566"},
            {"brand": "Xiaomi", "model": "POCO X5", "color": "Синий", "storage": "128",
             "battery": "5000 mAh", "imei": "555555555555555", "has_box": True,
             "price": Decimal("200"), "currency": Currency.USD,
             "account": cash_usd, "client_name": "Азиз", "client_contact": "+998905556677"},
            {"brand": "Huawei", "model": "P50", "color": "Чёрный", "storage": "256",
             "battery": "4100 mAh", "imei": "666666666666666", "has_box": True,
             "price": Decimal("350"), "currency": Currency.USD,
             "account": cash_usd, "client_name": "Улугбек", "client_contact": "+998906667788"},
            {"brand": "Oppo", "model": "Reno 8", "color": "Зелёный", "storage": "128",
             "battery": "4500 mAh", "imei": "777777777777777", "has_box": False,
             "price": Decimal("250"), "currency": Currency.USD,
             "account": cash_usd, "client_name": "Тимур", "client_contact": "+998907778899"},
            {"brand": "Apple", "model": "iPhone 12", "color": "Белый", "storage": "64",
             "battery": "2800 mAh", "imei": "888888888888888", "has_box": True,
             "price": Decimal("350"), "currency": Currency.USD,
             "account": cash_usd, "client_name": "Жасур", "client_contact": "+998908889900"},
        ]

        phones_created = []
        for data in purchases_data:
            purchase = PhonePurchase(
                client_name=data["client_name"],
                client_contact=data["client_contact"],
                brand=data["brand"], model=data["model"],
                color=data["color"], storage=data["storage"],
                battery=data["battery"], imei=data["imei"],
                has_box=data["has_box"], price=data["price"],
                currency=data["currency"],
                cash_account_id=data["account"].id,
            )
            db.session.add(purchase)
            db.session.flush()

            phone = Phone(purchase=purchase, status="in_stock")
            db.session.add(phone)
            db.session.flush()

            apply_transaction(
                account=data["account"], type_="expense", amount=data["price"],
                description=f"Закупка: {data['brand']} {data['model']}",
                source_type="purchase", source_id=purchase.id,
            )
            phones_created.append(phone)

        db.session.commit()

        # ===== 3. Простая продажа — iPhone 12 =====
        sale_phone = phones_created[7]
        sale = Sale(
            phone_id=sale_phone.id,
            client_name="Иванов Иван", client_contact="+998901234567",
            price=Decimal("420"), currency=Currency.USD,
            cash_account_id=cash_usd.id,
        )
        db.session.add(sale)
        db.session.flush()
        sale_phone.status = "sold"
        apply_transaction(
            account=cash_usd, type_="income", amount=Decimal("420"),
            description=f"Продажа: {sale_phone.brand} {sale_phone.model}",
            source_type="sale", source_id=sale.id,
        )
        db.session.commit()

        # ===== 4. Покупатели =====
        customers_data = [
            {"full_name": "Петров Пётр", "phone": "+998901234567",
             "phone_extra": "+998711234567", "passport": "AB1234567",
             "pinfl": "12345678901234", "address": "г. Ташкент, ул. Навои 1",
             "salary_day": 5},
            {"full_name": "Сидоров Сидор", "phone": "+998902345678",
             "phone_extra": "", "passport": "AC7654321",
             "pinfl": "43210987654321", "address": "г. Ташкент, ул. Амира Темура 10",
             "salary_day": 15},
            {"full_name": "Каримов Али", "phone": "+998903456789",
             "phone_extra": "", "passport": "AD1112223",
             "pinfl": "11122233344455", "address": "г. Самарканд, ул. Регистан 5",
             "salary_day": 25},
            {"full_name": "Юлдашев Акмаль", "phone": "+998904567890",
             "phone_extra": "", "passport": "AE9998887",
             "pinfl": "55566677788899", "address": "г. Ташкент, ул. Юнусабад 12",
             "salary_day": 10},
            {"full_name": "Рахимова Дилноза", "phone": "+998905678901",
             "phone_extra": "", "passport": "AF1112223",
             "pinfl": "99988877766655", "address": "г. Ташкент, ул. Чиланзар 20",
             "salary_day": 20},
        ]

        customers = []
        for c in customers_data:
            customer = Customer(**c)
            db.session.add(customer)
            db.session.flush()
            customers.append(customer)
        db.session.commit()

        # ===== 5. РАССРОЧКИ =====
        # --- 5.1 Просроченная: стартовала 3 месяца назад, оплачен только 1-й платёж ---
        inst_phone_1 = phones_created[0]  # iPhone 13
        inst_1 = Installment(
            phone_id=inst_phone_1.id,
            customer_id=customers[0].id,  # Петров
            price=Decimal("700"),
            prepayment=Decimal("200"),
            percent=Decimal("20"),
            months=5,
            currency=Currency.USD,
            started_at=datetime.utcnow() - timedelta(days=90),
        )
        db.session.add(inst_1)
        db.session.flush()

        apply_transaction(
            account=cash_usd, type_="income", amount=inst_1.prepayment,
            description=f"Предоплата по рассрочке #{inst_1.id}",
            source_type="installment_prepayment", source_id=inst_1.id,
        )
        db.session.add(InstallmentPayment(
            installment=inst_1, amount=inst_1.prepayment, currency=Currency.USD,
            cash_account_id=cash_usd.id, comment="Предоплата",
        ))
        # Первый платёж — оплачен
        apply_transaction(
            account=cash_usd, type_="income", amount=Decimal("120"),
            description=f"Платёж по рассрочке #{inst_1.id}",
            source_type="installment_payment", source_id=inst_1.id,
        )
        db.session.add(InstallmentPayment(
            installment=inst_1, amount=Decimal("120"), currency=Currency.USD,
            cash_account_id=cash_usd.id, comment="Первый платёж",
        ))
        inst_phone_1.status = "installment"

        # --- 5.2 Частично оплаченная: стартовала 1 месяц назад, оплачено 2 из 5 ---
        inst_phone_2 = phones_created[1]  # iPhone 14 Pro
        inst_2 = Installment(
            phone_id=inst_phone_2.id,
            customer_id=customers[1].id,  # Сидоров
            price=Decimal("1200"),
            prepayment=Decimal("300"),
            percent=Decimal("15"),
            months=5,
            currency=Currency.USD,
            started_at=datetime.utcnow() - timedelta(days=35),
        )
        db.session.add(inst_2)
        db.session.flush()

        apply_transaction(
            account=cash_usd, type_="income", amount=inst_2.prepayment,
            description=f"Предоплата по рассрочке #{inst_2.id}",
            source_type="installment_prepayment", source_id=inst_2.id,
        )
        db.session.add(InstallmentPayment(
            installment=inst_2, amount=inst_2.prepayment, currency=Currency.USD,
            cash_account_id=cash_usd.id, comment="Предоплата",
        ))
        apply_transaction(
            account=cash_usd, type_="income", amount=Decimal("200"),
            description=f"Платёж по рассрочке #{inst_2.id}",
            source_type="installment_payment", source_id=inst_2.id,
        )
        db.session.add(InstallmentPayment(
            installment=inst_2, amount=Decimal("200"), currency=Currency.USD,
            cash_account_id=cash_usd.id, comment="Частичный платёж",
        ))
        inst_phone_2.status = "installment"

        # --- 5.3 Полностью закрытая: стартовала 4 месяца назад, все платежи внесены ---
        inst_phone_3 = phones_created[2]  # Galaxy S22
        inst_3 = Installment(
            phone_id=inst_phone_3.id,
            customer_id=customers[2].id,  # Каримов
            price=Decimal("500"),
            prepayment=Decimal("100"),
            percent=Decimal("10"),
            months=3,
            currency=Currency.USD,
            started_at=datetime.utcnow() - timedelta(days=120),
        )
        db.session.add(inst_3)
        db.session.flush()

        apply_transaction(
            account=cash_usd, type_="income", amount=inst_3.prepayment,
            description=f"Предоплата по рассрочке #{inst_3.id}",
            source_type="installment_prepayment", source_id=inst_3.id,
        )
        db.session.add(InstallmentPayment(
            installment=inst_3, amount=inst_3.prepayment, currency=Currency.USD,
            cash_account_id=cash_usd.id, comment="Предоплата",
        ))
        # Вносим все 3 платежа — закрываем
        for amount in [Decimal("147"), Decimal("147"), Decimal("146")]:
            apply_transaction(
                account=cash_usd, type_="income", amount=amount,
                description=f"Платёж по рассрочке #{inst_3.id}",
                source_type="installment_payment", source_id=inst_3.id,
            )
            db.session.add(InstallmentPayment(
                installment=inst_3, amount=amount, currency=Currency.USD,
                cash_account_id=cash_usd.id, comment="Платёж",
            ))
        inst_3.is_closed = True
        inst_phone_3.status = "installment"

        # --- 5.4 Свежая активная: только предоплата, всё по графику ---
        inst_phone_4 = phones_created[3]  # Redmi Note 12
        inst_4 = Installment(
            phone_id=inst_phone_4.id,
            customer_id=customers[3].id,  # Юлдашев
            price=Decimal("300"),
            prepayment=Decimal("50"),
            percent=Decimal("10"),
            months=4,
            currency=Currency.USD,
            started_at=datetime.utcnow() - timedelta(days=5),
        )
        db.session.add(inst_4)
        db.session.flush()

        apply_transaction(
            account=cash_usd, type_="income", amount=inst_4.prepayment,
            description=f"Предоплата по рассрочке #{inst_4.id}",
            source_type="installment_prepayment", source_id=inst_4.id,
        )
        db.session.add(InstallmentPayment(
            installment=inst_4, amount=inst_4.prepayment, currency=Currency.USD,
            cash_account_id=cash_usd.id, comment="Предоплата",
        ))
        inst_phone_4.status = "installment"

        # --- 5.5 Сильно просроченная: стартовала 6 месяцев назад, оплачено только предоплата ---
        inst_phone_5 = phones_created[4]  # POCO X5
        inst_5 = Installment(
            phone_id=inst_phone_5.id,
            customer_id=customers[4].id,  # Рахимова
            price=Decimal("400"),
            prepayment=Decimal("50"),
            percent=Decimal("25"),
            months=4,
            currency=Currency.USD,
            started_at=datetime.utcnow() - timedelta(days=180),
        )
        db.session.add(inst_5)
        db.session.flush()

        apply_transaction(
            account=cash_usd, type_="income", amount=inst_5.prepayment,
            description=f"Предоплата по рассрочке #{inst_5.id}",
            source_type="installment_prepayment", source_id=inst_5.id,
        )
        db.session.add(InstallmentPayment(
            installment=inst_5, amount=inst_5.prepayment, currency=Currency.USD,
            cash_account_id=cash_usd.id, comment="Предоплата",
        ))
        inst_phone_5.status = "installment"

        db.session.commit()

        # ===== 6. Должники =====
        debtors_data = [
            {
                "full_name": "Ахмедов Ахмед", "phone": "+998901112233",
                "note": "Занял на ремонт", "loan_date": datetime.utcnow().date(),
                "transactions": [
                    {"type": "borrow", "amount": Decimal("1000"), "currency": Currency.USD,
                     "comment": "Взял на ремонт"},
                ],
            },
            {
                "full_name": "Юсупов Юсуп", "phone": "+998902223344",
                "note": "Занял на свадьбу", "loan_date": (datetime.utcnow() - timedelta(days=60)).date(),
                "transactions": [
                    {"type": "borrow", "amount": Decimal("500"), "currency": Currency.USD,
                     "comment": "Занял"},
                    {"type": "repay", "amount": Decimal("200"), "currency": Currency.USD,
                     "comment": "Вернул часть"},
                ],
            },
            {
                "full_name": "Набиев Рустам", "phone": "+998903334455",
                "note": "Долг в сумах", "loan_date": (datetime.utcnow() - timedelta(days=15)).date(),
                "transactions": [
                    {"type": "borrow", "amount": Decimal("5000000"), "currency": Currency.UZS,
                     "comment": "Занял наличными"},
                ],
            },
            {
                "full_name": "Исмаилов Шухрат", "phone": "+998904445566",
                "note": "Смешанный долг: USD и UZS",
                "loan_date": (datetime.utcnow() - timedelta(days=45)).date(),
                "transactions": [
                    {"type": "borrow", "amount": Decimal("800"), "currency": Currency.USD,
                     "comment": "Взял в долларах"},
                    {"type": "borrow", "amount": Decimal("3000000"), "currency": Currency.UZS,
                     "comment": "Взял в сумах"},
                    {"type": "repay", "amount": Decimal("300"), "currency": Currency.USD,
                     "comment": "Вернул часть USD"},
                ],
            },
        ]

        for d in debtors_data:
            txs = d.pop("transactions")
            debtor = Debtor(**d)
            db.session.add(debtor)
            db.session.flush()

            for tx in txs:
                db.session.add(DebtorTransaction(
                    debtor=debtor,
                    type=tx["type"],
                    amount=tx["amount"],
                    currency=tx["currency"],
                    comment=tx["comment"],
                ))
        db.session.commit()

        # ===== Итоги =====
        print("Готово. Создано:")
        print(f"  Касс: {CashAccount.query.count()}")
        print(f"  Закупок: {PhonePurchase.query.count()}")
        print(f"  Телефонов в наличии: {Phone.query.filter_by(status='in_stock').count()}")
        print(f"  Продаж: {Sale.query.count()}")
        print(f"  Покупателей: {Customer.query.count()}")
        print(f"  Рассрочек: {Installment.query.count()}")
        print(f"  Должников: {Debtor.query.count()}")


if __name__ == "__main__":
    seed()
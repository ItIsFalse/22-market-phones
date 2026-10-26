from app import create_app
from app.extensions import db
from app.models import Customer, PhonePurchase, Phone, Installment, InstallmentPayment, CashAccount, Currency
from app.services.cash import apply_transaction
from datetime import datetime
from decimal import Decimal

app = create_app()

with app.app_context():
    print("Начинаем добавление тестовых данных (6 рассрочек)...")

    # 1. Создаём клиентов
    customers_data = [
        {"name": "Алишер", "phone": "+998 90 111 22 33"},
        {"name": "Мадина", "phone": "+998 91 444 55 66"},
        {"name": "Тимур", "phone": "+998 93 777 88 99"},
        {"name": "Джасур", "phone": "+998 94 111 11 11"},
        {"name": "Лола", "phone": "+998 95 222 22 22"},
        {"name": "Сардор", "phone": "+998 97 333 33 33"},
    ]
    customers = []
    for c_data in customers_data:
        c = Customer.query.filter_by(phone=c_data["phone"]).first()
        if not c:
            c = Customer(full_name=c_data["name"], phone=c_data["phone"])
            db.session.add(c)
            db.session.flush()
        customers.append(c)

    # Получаем дефолтную USD кассу
    account = CashAccount.query.filter_by(currency=Currency.USD).first()
    if not account:
        print("Ошибка: Нет USD-кассы!")
        exit()

    # 2. Создаём телефоны (сразу помечаем, что они в рассрочке)
    phones_data = [
        {"brand": "iPhone", "model": "15 Pro Max", "imei": "111000111", "price": 1200, "color": "Titanium"},
        {"brand": "Samsung", "model": "S24 Ultra", "imei": "222000222", "price": 1000, "color": "Black"},
        {"brand": "Xiaomi", "model": "14 Pro", "imei": "333000333", "price": 800, "color": "White"},
        {"brand": "Google", "model": "Pixel 8", "imei": "444000444", "price": 600, "color": "Blue"},
        {"brand": "OnePlus", "model": "12", "imei": "555000555", "price": 500, "color": "Green"},
        {"brand": "Nothing", "model": "Phone (2)", "imei": "666000666", "price": 400, "color": "Transparent"},
    ]

    phones = []
    for p_data in phones_data:
        purchase = PhonePurchase(
            brand=p_data["brand"], model=p_data["model"], imei=p_data["imei"],
            price=Decimal(p_data["price"]), currency=Currency.USD,
            color=p_data["color"], cash_account_id=account.id
        )
        db.session.add(purchase)
        db.session.flush()

        phone = Phone(purchase_id=purchase.id, status="installment")  # Сразу в рассрочку
        db.session.add(phone)
        db.session.flush()

        # Списание за закупку
        apply_transaction(
            account=account, type_="expense", amount=Decimal(p_data["price"]),
            description=f"Закупка: {p_data['brand']} {p_data['model']}",
            source_type="purchase", source_id=purchase.id,
        )
        phones.append(phone)


    # 3. Вспомогательная функция для создания рассрочки
    def make_installment(phone, customer, price, prepayment, percent, months, payments_list, is_closed=False):
        inst = Installment(
            phone_id=phone.id, customer_id=customer.id,
            price=Decimal(str(price)), prepayment=Decimal(str(prepayment)),
            percent=Decimal(str(percent)), months=months,
            currency=Currency.USD, started_at=datetime.utcnow(), is_closed=is_closed
        )
        db.session.add(inst)
        db.session.flush()

        # Предоплата (если > 0)
        if inst.prepayment > 0:
            p = InstallmentPayment(installment=inst, amount=inst.prepayment, currency=Currency.USD,
                                   cash_account_id=account.id, comment="Предоплата")
            db.session.add(p);
            db.session.flush()
            apply_transaction(account=account, type_="income", amount=p.amount, description="Предоплата",
                              source_type="installment_prepayment", source_id=inst.id, payment_id=p.id)

        # Остальные платежи
        for pay_amount in payments_list:
            p = InstallmentPayment(installment=inst, amount=Decimal(str(pay_amount)), currency=Currency.USD,
                                   cash_account_id=account.id, comment="Платёж")
            db.session.add(p);
            db.session.flush()
            apply_transaction(account=account, type_="income", amount=p.amount, description="Платёж",
                              source_type="installment_payment", source_id=inst.id, payment_id=p.id)

        return inst


    # 4. Создаём 6 разных рассрочек

    # 1. Огромный процент (100%), много месяцев, мало оплачено
    make_installment(phones[0], customers[0], price=1500, prepayment=100, percent=100, months=12,
                     payments_list=[100, 100])

    # 2. Нулевой процент, закрыта полностью
    make_installment(phones[1], customers[1], price=1000, prepayment=200, percent=0, months=4,
                     payments_list=[200, 200, 200, 200], is_closed=True)

    # 3. 50% предоплата, 0% процент, закрыта
    make_installment(phones[2], customers[2], price=800, prepayment=400, percent=0, months=2, payments_list=[200, 200],
                     is_closed=True)

    # 4. 15% процент, оплачен 1 месяц (активная)
    make_installment(phones[3], customers[3], price=600, prepayment=50, percent=15, months=6, payments_list=[100])

    # 5. Большая цена, 30% процент, оплачено 3 месяца
    make_installment(phones[4], customers[4], price=2000, prepayment=500, percent=30, months=10,
                     payments_list=[150, 150, 150])

    # 6. Маленькая цена, 5% процент, 24 месяца, оплачено 6 месяцев
    make_installment(phones[5], customers[5], price=400, prepayment=0, percent=5, months=24,
                     payments_list=[20, 20, 20, 20, 20, 20])

    db.session.commit()
    print("Готово! Создано 6 рассрочек с разными параметрами.")
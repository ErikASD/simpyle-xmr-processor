from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, exists
from sqlalchemy.orm import relationship
from database import Base
import time
from uuid import uuid4
from hashlib import sha256
import random
from sqlalchemy import or_, insert

def get_uuid():
    return str(uuid4())

def get_current_time():
    return int(time.time())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=get_uuid)
    display = Column(String, unique=True, index=True)
    balance = Column(Integer, default=0)
    xmr_address = Column(String, unique=True, index=True)
    xmr_address_index = Column(Integer, unique=True, index=True)
    public_fingerprint = Column(String, unique=True, index=True)
    login_codes = relationship("LoginCode", back_populates="user", order_by='LoginCode.time_created.desc()')
    transactions = relationship("Transaction", back_populates="user", order_by='Transaction.time_created.desc()')
    withdraw_requests = relationship("WithdrawRequest", back_populates="user", order_by='WithdrawRequest.time_created.desc()')
    time_created = Column(Integer, default=get_current_time)

    def create(db, display, public_fingerprint, login_code):
        db_user = User.get_by_public_fingerprint(db, public_fingerprint)
        if db_user:
            return db_user

        while User.exists(db, display):
            display += str(random.randint(0, 9))

        db_user = User(
            display = display,
            public_fingerprint = public_fingerprint,
        )
        db.add(db_user)
        login_code.user = db_user
        db.commit()
        db.refresh(db_user)
        return db_user

    def login(login_code):
        return login_code.user

    def exists(db, display):
        exist = db.scalar(exists().where(User.display == display).select())
        return exist

    def get(db, id):
        user = db.query(User).filter(User.id == id).one_or_none()
        return user

    def get_by_display(db, display):
        user = db.query(User).filter(User.display == display).one_or_none()
        return user

    def get_by_public_fingerprint(db, public_fingerprint):
        user = db.query(User).filter(User.public_fingerprint == public_fingerprint).one_or_none()
        return user

    def balance_deduct(self, db, amount):
        if (self.balance - amount) < 0:
            return False
        self.balance -= amount
        db.commit()
        return True

    def balance_add(self, db, amount):
        self.balance += amount
        db.commit()

    def create_address(self, db, address):
        self.xmr_address = address["address"]
        self.xmr_address_index = address["address_index"]
        db.commit()

class LoginCode(Base):
    __tablename__ = "login_codes"

    id = Column(String, primary_key=True, default=get_uuid)
    public_fingerprint = Column(String, index=True)
    code = Column(String, index=True)
    user_id = Column(String, ForeignKey("users.id"))
    user = relationship("User", back_populates="login_codes")
    time_created = Column(Integer, default=get_current_time)

    def create(db, public_fingerprint, code):
        db_user = User.get_by_public_fingerprint(db, public_fingerprint)
        user_id = db_user.id if db_user else None
        db_login_code = LoginCode(
            public_fingerprint = public_fingerprint,
            user_id = user_id,
            code = code,
        )
        db.add(db_login_code)
        db.commit()
        db.refresh(db_login_code)
        return db_login_code

    def get(db, public_fingerprint, code):
        db_login_code = db.query(LoginCode).filter(LoginCode.public_fingerprint == public_fingerprint, LoginCode.code == code).order_by(LoginCode.time_created.desc()).one_or_none()
        return db_login_code

    def delete_expired(db, expire_time):
        query = LoginCode.__table__.delete().where(LoginCode.time_created < int(time.time()) - expire_time)
        db.execute(query)
        db.commit()

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String, primary_key=True, default=get_uuid)
    address_index = Column(Integer, ForeignKey("users.xmr_address_index"), index=True)
    user = relationship("User", back_populates="transactions")
    amount = Column(Integer, index=True)
    tx_hash = Column(String, index=True, unique=True)
    unlocked = Column(Boolean, default=False, index=True)
    block_height = Column(Integer, index=True)
    credited = Column(Boolean, default=False, index=True)
    time_created = Column(Integer, default=get_current_time)

    def bulk_insert(db, transactions):
        for transaction in transactions:
            transaction["address_index"] = transaction["subaddr_index"]["minor"]
        db.execute(insert(Transaction).prefix_with("OR IGNORE"),transactions)
        db.commit()

    def get_by_tx_hash(db, tx_hash):
        db_transaction = db.query(Transaction).filter(Transaction.tx_hash == tx_hash).one_or_none()
        return db_transaction

    def get_by_tx_hashes(db, tx_hashes):
        filter_arg = []
        for tx in tx_hashes:
            filter_arg.append(Transaction.tx_hash == tx)
        db_transaction = db.query(Transaction).filter(or_(*filter_arg)).all()
        return db_transaction

    def get_by_tx_hashes_no_credit(db, tx_hashes):
        filter_arg = []
        for tx in tx_hashes:
            filter_arg.append(Transaction.tx_hash == tx)
        db_transaction = db.query(Transaction).filter(Transaction.credited == False).filter(or_(*filter_arg)).all()
        return db_transaction

    def exists(db, tx_hash):
        exist = db.scalar(exists().where(Transaction.tx_hash == tx_hash).select())
        return exist

    def get_user(self, db):
        db_user = db.query(User).filter(User.xmr_address_index == self.address_index).one_or_none()
        return db_user

    def credit(self, db):
        if not self.credited:
            if self.user:
                self.user.balance += self.amount
            self.unlocked = True
            self.credited = True
            db.commit()

class WithdrawRequest(Base):
    __tablename__ = "withdraw_requests" #used to monitor withdraws, if one stays unsuccessful for a while, error occured somehow, most likely server restart during withdraw call

    id = Column(String, primary_key=True, default=get_uuid)
    address_index = Column(Integer, ForeignKey("users.xmr_address_index"), index=True)
    user = relationship("User", back_populates="withdraw_requests")
    amount = Column(Integer)
    fee = Column(Integer, default=None)
    tx_hash = Column(String, default=None, index=True)
    success = Column(Boolean, default=False, index=True)
    refunded = Column(Boolean, default=False, index=True)
    time_created = Column(Integer, default=get_current_time)

    def create(db, user, amount):
        db_withdraw_request = WithdrawRequest(
            address_index = user.xmr_address_index,
            amount = amount
        )
        db.add(db_withdraw_request)
        db.commit()
        db.refresh(db_withdraw_request)
        return db_withdraw_request

    def succeed(self, db, fee, tx_hash):
        self.success = True
        self.fee = fee
        self.tx_hash = tx_hash
        db.commit()

    def refund(self, db):
        if not (self.refunded or self.success):
            self.refunded = True
            self.user.balance_add(db, self.amount)
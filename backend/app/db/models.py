
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AccountType(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    SYSTEM = "SYSTEM"


class TransactionStatus(str, enum.Enum):
    PENDING = "PENDING"
    POSTED = "POSTED"
    FAILED = "FAILED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    accounts: Mapped[list["Account"]] = relationship(back_populates="user")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # NULL for system accounts such as SYSTEM_FUNDING
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100))
    account_type: Mapped[AccountType] = mapped_column(Enum(AccountType, name="account_type"))
    currency: Mapped[str] = mapped_column(String(3))  # ISO 4217, e.g. USD
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User | None"] = relationship(back_populates="accounts")
    entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="account")
    __table_args__ = (
        UniqueConstraint("id", "currency", name="uq_accounts_id_currency"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_accounts_currency_format"),
    )

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)  # rule I7
    description: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus, name="transaction_status"),
        default=TransactionStatus.PENDING,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    entries: Mapped[list["LedgerEntry"]] = relationship(back_populates="transaction")


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "currency"],
            ["accounts.id", "accounts.currency"],
            name="fk_ledger_entries_account_currency",
        ),
        CheckConstraint("amount <> 0", name="ck_ledger_entries_amount_nonzero"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_ledger_entries_currency_format"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    transaction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("transactions.id"))  # rule I8
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"))  # rule I8
    amount: Mapped[int] = mapped_column(BigInteger)  # cents, rules R1 and R3
    currency: Mapped[str] = mapped_column(String(3))  # rule I2
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transaction: Mapped["Transaction"] = relationship(back_populates="entries")
    account: Mapped["Account"] = relationship(back_populates="entries")

from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.db.models import User, Account, AccountType
  
from app.db.session import engine, SessionLocal
from app.schemas.user import UserCreate, UserResponse
from app.schemas.account import AccountCreate, AccountResponse

app = FastAPI(title="FinGuard API")


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/users", response_model=UserResponse, status_code=201)
def create_user(data: UserCreate):
    with SessionLocal() as db:
        user = User(
            email=data.email,
            full_name=data.full_name
        )

        db.add(user)

        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Email already registered"
            )

        db.refresh(user)
        return user
        
@app.post("/accounts", response_model=AccountResponse, status_code=201)
def create_account(data: AccountCreate):
    with SessionLocal() as db:

        # Verify that the user exists
        user = db.get(User, data.user_id)

        if user is None:
            raise HTTPException(
                status_code=404,
                detail="User not found"
            )

        # Create a CUSTOMER account
        account = Account(
            user_id=data.user_id,
            name=data.name,
            account_type=AccountType.CUSTOMER,
            currency=data.currency
        )

        db.add(account)
        db.commit()
        db.refresh(account)

        return account


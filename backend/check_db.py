from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg://finguard:finguard@localhost:5432/finguard")
with engine.connect() as conn:
    print(conn.execute(text("select version()")).scalar())
    
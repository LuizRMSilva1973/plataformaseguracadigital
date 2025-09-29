import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.models import Plan

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def seed_plans():
    db = SessionLocal()
    try:
        # Check if plans already exist
        if db.query(Plan).count() == 0:
            print("Seeding plans...")
            basic_plan = Plan(
                name="Basic",
                price=1000,  # $10.00
                stripe_price_id="price_12345", # Replace with your actual Stripe Price ID
                features=["Feature 1", "Feature 2"]
            )
            pro_plan = Plan(
                name="Pro",
                price=2500,  # $25.00
                stripe_price_id="price_67890", # Replace with your actual Stripe Price ID
                features=["Feature 1", "Feature 2", "Feature 3", "IP Reputation"]
            )
            db.add(basic_plan)
            db.add(pro_plan)
            db.commit()
            print("Plans seeded.")
        else:
            print("Plans already seeded.")
    finally:
        db.close()

if __name__ == "__main__":
    seed_plans()

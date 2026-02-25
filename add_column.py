"""One-time script to add max_lessons_per_subject_per_day column"""
from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    try:
        db.session.execute(text(
            "ALTER TABLE schedule_settings ADD COLUMN max_lessons_per_subject_per_day INTEGER DEFAULT 2"
        ))
        db.session.commit()
        print("Column added successfully")
    except Exception as e:
        err = str(e).lower()
        if "duplicate column name" in err or "already exists" in err:
            print("Column already exists, skipping")
        else:
            raise

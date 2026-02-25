"""One-time script to add classroom scenario columns (migration 3)"""
from app import create_app, db
from sqlalchemy import text

app = create_app()
with app.app_context():
    conn = db.session.connection()

    def add_col(table, col, sql_type, default=None):
        try:
            extra = f" DEFAULT {default}" if default else ""
            conn.execute(text(
                f"ALTER TABLE {table} ADD COLUMN {col} {sql_type}{extra}"
            ))
            print(f"  + {table}.{col}")
        except Exception as e:
            err = str(e).lower()
            if "duplicate column name" in err or "already exists" in err:
                print(f"  - {table}.{col} (already exists)")
            else:
                raise

    print("Adding classroom scenario columns...")
    add_col("subjects", "requires_fixed_classroom", "INTEGER", "0")
    add_col("subjects", "default_classroom_id", "INTEGER")
    add_col("teachers", "home_classroom_id", "INTEGER")
    add_col("school_classes", "home_classroom_id", "INTEGER")
    add_col("schedule_settings", "classroom_mode", "VARCHAR(20)", "'class_room'")
    add_col("schedule_settings", "elementary_group_subjects_leave", "INTEGER", "1")

    db.session.commit()
    print("Done.")

    # Mark migration 3 as applied in Alembic
    try:
        conn.execute(text(
            "UPDATE alembic_version SET version_num = '3add_classroom'"
        ))
        db.session.commit()
        print("Alembic version updated to 3add_classroom")
    except Exception as e:
        print("Note: Could not update alembic_version:", e)

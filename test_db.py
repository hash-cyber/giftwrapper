from config import get_db_connection

print("Starting test...")

conn = get_db_connection()

if conn:
    print("DB Connected ✅")
else:
    print("DB Failed ❌")
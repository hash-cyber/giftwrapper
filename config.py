import os
import psycopg2

def get_db_connection():
    conn = psycopg2.connect(
        host=os.getenv("dpg-d7b8074hg0os73ab80j0-a"),
        database=os.getenv("giftwrapper_db_gstu"),
        user=os.getenv("giftwrapper_db_gstu_userr"),
        password=os.getenv("GDQOl0GXa6Crj5f45nEZCl1y4DgAw7iM"),
        port=os.getenv("5432")
    )
    return conn
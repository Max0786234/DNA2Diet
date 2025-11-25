"""Check analysis status for a user"""
import sys
sys.path.insert(0, '.')

from app import mysql

email = 'vishaljha304@gmail.com'

cur = mysql.connection.cursor()
cur.execute("SELECT id FROM users WHERE email = %s", (email,))
user = cur.fetchone()

if user:
    user_id = user[0]
    cur.execute("""
        SELECT id, genome_filename, status, error_message, created_at, completed_at
        FROM analyses 
        WHERE user_id = %s 
        ORDER BY created_at DESC 
        LIMIT 5
    """, (user_id,))
    analyses = cur.fetchall()
    
    print(f"User ID: {user_id}")
    print(f"Found {len(analyses)} analyses:")
    for a in analyses:
        print(f"\nAnalysis ID: {a[0]}")
        print(f"  File: {a[1]}")
        print(f"  Status: {a[2]}")
        print(f"  Error: {a[3] if a[3] else 'None'}")
        print(f"  Created: {a[4]}")
        print(f"  Completed: {a[5] if a[5] else 'Not completed'}")
else:
    print("User not found")

cur.close()


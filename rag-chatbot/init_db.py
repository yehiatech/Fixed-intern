from db import get_connection
import hashlib

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def init_db():
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
                
                cur.execute('''
                CREATE TABLE IF NOT EXISTS organizations (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    name VARCHAR(255) UNIQUE NOT NULL,
                    status VARCHAR(50) DEFAULT 'Active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                ''')
                
                cur.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'Active';")
                
                cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    username VARCHAR(255) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                ''')
                
                cur.execute('''
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id VARCHAR(50) PRIMARY KEY,
                    organization_id UUID REFERENCES organizations(id) ON DELETE CASCADE NOT NULL,
                    customer_name VARCHAR(255),
                    phone_number VARCHAR(50),
                    issue_description TEXT,
                    status VARCHAR(50) DEFAULT 'open',
                    agent_id UUID REFERENCES users(id) ON DELETE SET NULL,
                    ai_transcript JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                ''')

                # Seed superadmin
                super_pw = hash_pw("123")
                cur.execute('''
                INSERT INTO users (username, password_hash, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (username) DO NOTHING;
                ''', ("superadmin", super_pw, "super_admin"))
                
                # Seed a mock organization
                cur.execute('''
                INSERT INTO organizations (name, status)
                VALUES (%s, %s)
                ON CONFLICT (name) DO NOTHING;
                ''', ("Mock Org", "Active"))
                
                cur.execute("SELECT id FROM organizations WHERE name = 'Mock Org'")
                org_row = cur.fetchone()
                if org_row:
                    org_id = org_row[0]
                    # Seed admin_user
                    cur.execute('''
                    INSERT INTO users (username, password_hash, role, organization_id)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (username) DO NOTHING;
                    ''', ("admin_user", super_pw, "org_admin", org_id))
                    
        print("Database tables initialized successfully. Superadmin and admin_user seeded.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()

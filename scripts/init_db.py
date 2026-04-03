from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.models import User


def main():
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == 'admin').first():
            db.add(User(username='admin', password_hash=hash_password('ChangeMe123!')))
            db.commit()
            print('admin user created: admin / ChangeMe123!')
        else:
            print('admin already exists')
    finally:
        db.close()


if __name__ == '__main__':
    main()

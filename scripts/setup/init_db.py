from app.core.database import engine
from app.models.database import Base
from app.models.database.user import User
from app.models.database.file import File
from app.models.database.query import Query


def main() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    main()



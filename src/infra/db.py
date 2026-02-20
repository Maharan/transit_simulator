from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")


class Database(object):
    def __init__(
        self, url=os.getenv("DATABASE_URL_LOCAL") or os.getenv("DATABASE_URL")
    ):
        self._engine = create_engine(url)

    def session(self):
        return Session(self._engine)

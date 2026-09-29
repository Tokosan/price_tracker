import os
from pathlib import Path

# Antes de importar la app: sin scheduler, sin Telegram y con una DB temporal.
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ.setdefault("SECRET_KEY", "clave-de-test")

import pytest

from tracker import db as dbmod
from tracker.models import Base

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(processor: str, name: str) -> str:
    return (FIXTURES / processor / name).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def database(tmp_path):
    dbmod.configure(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(dbmod.engine)
    yield dbmod
    dbmod.engine.dispose()


@pytest.fixture
def session():
    with dbmod.SessionLocal() as s:
        yield s

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from alembic import command
from tracker import db as dbmod
from tracker.models import Base


def test_migraciones_coinciden_con_los_modelos(tmp_path):
    dbmod.configure(f"sqlite:///{tmp_path}/mig.db")
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{tmp_path}/mig.db")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []

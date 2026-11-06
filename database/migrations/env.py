from alembic import context
from app.models import Base
from app.db import engine

target_metadata = Base.metadata
if context.is_offline_mode():
    raise RuntimeError('Migrations offline non prises en charge : vérifier la base cible avant migration.')
else:
    with engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

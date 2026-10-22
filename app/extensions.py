"""Flask extension singletons, initialised in the app factory."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from flask_bcrypt import Bcrypt
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.query import Query
from flask_wtf import CSRFProtect
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Typed declarative base; Flask-SQLAlchemy attaches the `query` property at runtime."""

    query: ClassVar[Query]


db = SQLAlchemy(model_class=Base)

if TYPE_CHECKING:  # mypy sees a real class; at runtime models use Flask-SQLAlchemy's bound Model
    Model = Base
else:
    Model = db.Model
bcrypt = Bcrypt()
login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])

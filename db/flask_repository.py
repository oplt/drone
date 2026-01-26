"""
Synchronous repository for Flask
Uses sync database connections to avoid event loop conflicts
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import select
from .flask_session import get_sync_session
from .models import User, Settings


class FlaskUserRepository:
    """Synchronous user repository for Flask"""

    def create_user(
        self, username: str, email: str, password: str, is_admin: bool = False
    ) -> User:
        """Create a new user (synchronous)"""
        with get_sync_session() as session:
            user = User(username=username, email=email, is_admin=is_admin)
            user.set_password(password)
            session.add(user)
            session.commit()
            session.refresh(user)
            return user

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get user by ID (synchronous)"""
        with get_sync_session() as session:
            result = session.execute(select(User).where(User.id == user_id))
            return result.scalar_one_or_none()

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username (synchronous)"""
        with get_sync_session() as session:
            result = session.execute(select(User).where(User.username == username))
            return result.scalar_one_or_none()

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email (synchronous)"""
        with get_sync_session() as session:
            result = session.execute(select(User).where(User.email == email))
            return result.scalar_one_or_none()

    def authenticate_user(
        self, username_or_email: str, password: str
    ) -> Optional[User]:
        """Authenticate user by username/email and password (synchronous)"""
        # Try username first
        user = self.get_user_by_username(username_or_email)
        if not user:
            # Try email
            user = self.get_user_by_email(username_or_email)

        if user and user.check_password(password) and user.is_active:
            # Update last login
            with get_sync_session() as session:
                merged_user = session.merge(user)
                merged_user.last_login = datetime.now(timezone.utc)
                session.commit()
                session.refresh(merged_user)
            return merged_user
        return None

    def update_user(self, user_id: int, **kwargs) -> Optional[User]:
        """Update user information (synchronous)"""
        with get_sync_session() as session:
            result = session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if user:
                for key, value in kwargs.items():
                    if key == "password":
                        user.set_password(value)
                    elif hasattr(user, key):
                        setattr(user, key, value)

                session.commit()
                session.refresh(user)
                return user
            return None

    def delete_user(self, user_id: int) -> bool:
        """Soft delete user (deactivate) (synchronous)"""
        with get_sync_session() as session:
            result = session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if user:
                user.is_active = False
                session.commit()
                return True
            return False


class FlaskSettingsRepository:
    """Synchronous configuration repository for Flask"""

    def get_configuration(self, user_id: Optional[int] = None) -> Optional[Settings]:
        """Get configuration for user (or global if user_id is None) (synchronous)"""
        with get_sync_session() as session:
            if user_id:
                result = session.execute(
                    select(Settings).where(Settings.user_id == user_id)
                )
            else:
                result = session.execute(
                    select(Settings).where(Settings.user_id.is_(None))
                )
            return result.scalar_one_or_none()

    def create_or_update_configuration(
        self, user_id: Optional[int] = None, **kwargs
    ) -> Settings:
        """Create or update configuration (synchronous)"""
        with get_sync_session() as session:
            # Try to get existing configuration
            if user_id:
                result = session.execute(
                    select(Settings).where(Settings.user_id == user_id)
                )
            else:
                result = session.execute(
                    select(Settings).where(Settings.user_id.is_(None))
                )
            config = result.scalar_one_or_none()

            if config:
                # Update existing configuration
                for key, value in kwargs.items():
                    if hasattr(config, key) and value is not None:
                        setattr(config, key, value)
                config.updated_at = datetime.now(timezone.utc)
            else:
                # Create new configuration
                config = Settings(user_id=user_id)
                for key, value in kwargs.items():
                    if hasattr(config, key) and value is not None:
                        setattr(config, key, value)
                session.add(config)

            session.commit()
            session.refresh(config)
            return config

    def get_configuration_dict(self, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Get configuration as dictionary (synchronous)"""
        config = self.get_configuration(user_id)
        if not config:
            return {}

        # Convert configuration to dictionary, excluding None values
        config_dict = {}
        for key in dir(config):
            if not key.startswith("_") and key not in ["metadata", "registry"]:
                try:
                    value = getattr(config, key)
                    if value is not None and not callable(value):
                        config_dict[key] = value
                except Exception:
                    pass

        return config_dict

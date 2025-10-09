from app.config import get_settings
from app.models.app_setting import AppSetting


class SettingsManager:
    def __init__(self, db_session):
        self._db = db_session
        self._static = get_settings()

    def get(self, key: str, default=None):
        # Dynamic value overrides static
        dynamic_value = self._get_from_db(key)
        return (
            dynamic_value
            if dynamic_value is not None
            else getattr(self._static, key, default)
        )

    def set(self, key: str, value: str):
        setting = self._db.query(AppSetting).filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            self._db.add(AppSetting(key=key, value=value))
        self._db.commit()

    def _get_from_db(self, key: str):
        setting = self._db.query(AppSetting).filter_by(key=key).first()
        return setting.value if setting else None

    def __getattr__(self, name):
        """
        Allow attribute-style access: config.database_url
        Dynamic settings take precedence over static ones.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        return self.get(name)

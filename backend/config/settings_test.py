from config.settings import *  # noqa: F401,F403

# 本地无 PostgreSQL 时用 SQLite 跑测试
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

"""
Set dummy environment variables before any app module is imported.
pydantic-settings reads env vars at Settings() instantiation time,
so these must be set before any import of app.config (which is
transitively imported by almost everything under app/).
"""
import os

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "1234567890:AABBCCDDEEFFaabbccddeeff-1234567890")
os.environ.setdefault("TELEGRAM_ADMIN_CHAT_ID", "-100123456789")
os.environ.setdefault("TELEGRAM_LOWKEY_CHAT_ID", "-100987654321")

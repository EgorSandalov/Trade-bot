import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
COMMUNITY_NAME = os.getenv("COMMUNITY_NAME", "Lobster")

_BASE_DIR = Path(__file__).resolve().parent.parent
PROFILES_DATABASE_PATH = Path(
    os.getenv("PROFILES_DATABASE_PATH", str(_BASE_DIR / "data" / "profiles.db"))
)
if not PROFILES_DATABASE_PATH.is_absolute():
    PROFILES_DATABASE_PATH = _BASE_DIR / PROFILES_DATABASE_PATH

from bot.groups import CONFIGURED_GROUPS, get_group, primary_group, primary_chat_id

_admin_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS: set[int] = {
    int(x.strip()) for x in _admin_raw.split(",") if x.strip().isdigit()
}

# Погрешность для определения закрытия в БУ (%)
BREAKEVEN_THRESHOLD_PCT = float(os.getenv("BREAKEVEN_THRESHOLD_PCT", "0.2"))

# Прокси для доступа к api.telegram.org (если без VPN не подключается)
# Пример: http://127.0.0.1:7890
PROXY_URL = os.getenv("PROXY_URL", "").strip() or None

# Minimum personal move % to send user's epic-trade sticker on close
EPIC_TRADE_PERSONAL_PCT = 100.0
EPIC_LOSS_TRADE_PERSONAL_PCT = -100.0
GROUP_BANNER_PATH = Path(os.getenv("GROUP_BANNER_PATH", str(_BASE_DIR / "assets" / "group_banner.png")))
PROFILE_PHOTOS_DIR = Path(os.getenv("PROFILE_PHOTOS_DIR", str(_BASE_DIR / "data" / "profiles")))

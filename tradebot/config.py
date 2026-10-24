"""Réglages du robot. Modifiables ici ou par variables d'environnement."""
import os
from pathlib import Path

# Actifs suivis : nom affiché -> paire Binance
SYMBOLS = {
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
    "OR": "PAXGUSDT",  # PAXG = 1 once d'or physique, suit le cours de l'or
    "SOL": "SOLUSDT",
    "BNB": "BNBUSDT",
    "XRP": "XRPUSDT",
    "DOGE": "DOGEUSDT",
    "ADA": "ADAUSDT",
    "AVAX": "AVAXUSDT",
    "LINK": "LINKUSDT",
}

TIMEFRAMES = ["1h", "4h", "1d"]
ENTRY_TF = "1h"          # unité de temps des signaux d'entrée
HISTORY_BARS = 300

# Compte simulé
START_CAPITAL = float(os.getenv("START_CAPITAL", 10000))
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PCT", 1.0))   # % du capital risqué par trade
DAILY_LOSS_LIMIT_PCT = 3.0                               # plus de nouveaux trades au-delà
FEE_PCT = 0.10                                           # frais par côté (Binance standard)
SLIPPAGE_BPS = 5                                         # 0,05 % de glissement
MAX_LEVERAGE = 1.0
MAX_OPEN_TRADES = 4    # les cryptos bougent souvent ensemble : on limite l'exposition simultanée

# Gestion de trade
TARGET1_R = 1.5          # moitié de la position clôturée ici, stop remonté au prix d'entrée
TARGET2_R = 3.0
MIN_STOP_ATR = 1.0
MAX_STOP_ATR = 3.0

# Actualités
NEWS_REFRESH_SEC = 600
NEWS_PAUSE_MIN = 60      # pas de nouvelle entrée sur un actif après une actu à fort impact

# Sources Binance (API publique « market data », sans clé)
REST_URL = os.getenv("BINANCE_REST", "https://data-api.binance.vision")
WS_URL = os.getenv("BINANCE_WS", "wss://data-stream.binance.vision/stream")
POLL_FALLBACK_SEC = 2    # si le flux temps réel tombe, interrogation toutes les 2 s

# Site
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8080))
DASH_PASSWORD = os.getenv("DASH_PASSWORD", "")  # vide = site public

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

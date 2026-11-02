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

TIMEFRAMES = ["15m", "1h", "4h", "1d"]
ENTRY_TF = "1h"          # (compte A) unité de temps des signaux d'entrée

# Deux comptes simulés indépendants, même marché, règles différentes
ACCOUNTS = {
    "A": {"label": "Sélectif (1h)", "entry": "1h", "trends": ("1d", "4h"), "file": "state.json"},
    "B": {"label": "Day trading (15 min)", "entry": "15m", "trends": ("4h", "1h"), "file": "state_B.json"},
    # Stratégie différente : cassure de canal journalière (type « Turtle »), testée sur 2019-2026
    "C": {"label": "Tendance journalière (cassure 55 j)", "entry": "1d", "kind": "breakout", "file": "state_C.json",
          "desc": "Achat si la clôture journalière dépasse le plus haut des 55 jours précédents et que l'EMA50 > EMA200 "
                  "(vente à découvert dans le cas inverse). Stop à 2 ATR. Sortie quand la clôture repasse sous le plus bas "
                  "des 20 jours (au-dessus du plus haut des 20 jours pour une vente). Pas d'objectif fixe : on laisse courir "
                  "les tendances. Peu de trades (environ 1 à 3 par mois), beaucoup de petites pertes et quelques gros gains."},
}
BREAKOUT_ENTRY_DAYS = 55
BREAKOUT_EXIT_DAYS = 20
BREAKOUT_STOP_ATR = 2.0
HISTORY_BARS = 300

# Compte simulé
START_CAPITAL = float(os.getenv("START_CAPITAL", 10000))
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PCT", 1.0))   # % du capital risqué par trade
DAILY_LOSS_LIMIT_PCT = 3.0                               # plus de nouveaux trades au-delà
# Les ventes à découvert sont impossibles au comptant : elles passent par les contrats perpétuels (futures).
FEE_PCT = 0.05                                           # frais par côté (futures Binance, ordre au marché)
FUNDING_8H_PCT = 0.01                                    # coût de financement estimé, toutes les 8 h
SLIPPAGE_BPS = 5                                         # 0,05 % de glissement
MAX_LEVERAGE = 3.0     # futures : le risque reste 1 % par trade, le levier évite de rétrécir les trades suivants
MAX_COST_SHARE = 0.5   # refuse un trade si frais + glissement > 50 % de l'écart entrée-stop
MAX_OPEN_TRADES = 4    # les cryptos bougent souvent ensemble : on limite l'exposition simultanée
MAX_SAME_SIDE = 3      # pas plus de 3 trades ouverts dans le même sens

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

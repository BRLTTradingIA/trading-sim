"""Actualités géopolitiques, macro et crypto via des flux RSS gratuits (sans clé).
Classement par mots-clés : c'est un filtre simple, pas une compréhension du texte."""
import asyncio
import hashlib
import logging
import re
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import aiohttp

from . import config

log = logging.getLogger("news")

G = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{lang}"
FEEDS = {
    "Google Actualités (géopolitique)": G.format(q="g%C3%A9opolitique+OR+guerre+OR+sanctions", hl="fr", gl="FR", lang="fr"),
    "Google News (geopolitics)": G.format(q="geopolitics+OR+war+OR+sanctions+OR+tariffs", hl="en-US", gl="US", lang="en"),
    "Google News (banques centrales)": G.format(q="Federal+Reserve+OR+ECB+OR+inflation+rates", hl="en-US", gl="US", lang="en"),
    "Google News (or)": G.format(q="gold+price", hl="en-US", gl="US", lang="en"),
    "Google News (crypto)": G.format(q="bitcoin+OR+ethereum+OR+solana+OR+XRP", hl="en-US", gl="US", lang="en"),
    "BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
}

ASSET_WORDS = {
    "BTC": r"\bbitcoin|\bbtc\b|\bcrypto",
    "ETH": r"\bethereum|\bether\b|\beth\b|\bcrypto",
    "SOL": r"\bsolana|\bsol\b|\bcrypto",
    "BNB": r"\bbnb\b|binance|\bcrypto",
    "XRP": r"\bxrp\b|ripple|\bcrypto",
    "DOGE": r"dogecoin|\bdoge\b|\bcrypto",
    "ADA": r"cardano|\bada\b|\bcrypto",
    "AVAX": r"avalanche|\bavax\b|\bcrypto",
    "LINK": r"chainlink|\blink\b token|\bcrypto",
    "OR": r"\bgold\b|\bl'or\b|\bprix de l.or|\bbullion|\bprecious metal|\bm[ée]taux pr[ée]cieux",
}
THEMES = {
    "géopolitique": r"g[ée]opolit|tension|middle east|moyen-orient|gaza|houthi|red sea|mer rouge|\bwar\b|\bguerre|invasion|missile|nuclear|nucl[ée]aire|\battack|\battaque|ceasefire|cessez-le-feu|sanction|military|militaire|conflict|conflit|iran|israel|isra[ëe]l|ukraine|russia|russie|china|chine|taiwan",
    "banques centrales": r"\bfed\b|federal reserve|fomc|powell|\becb\b|\bbce\b|lagarde|interest rate|taux directeur|rate cut|rate hike|baisse des taux|hausse des taux",
    "macro": r"inflation|\bcpi\b|jobs report|payrolls|recession|r[ée]cession|\bgdp\b|\bpib\b|tariff|droits de douane|dollar",
    "régulation crypto": r"\bsec\b|\betf\b|regulat|r[ée]glementation|\bban\b|interdiction",
    "incident crypto": r"\bhack|exploit|piratage|liquidation|insolvency|faillite",
}
# Événements qui font bouger les marchés d'un coup : on évite d'ouvrir un trade juste après.
HIGH_IMPACT = r"rate decision|d[ée]cision.{0,20}taux|fomc|rate cut|rate hike|cpi\b|jobs report|payrolls|\bhack|piratage|exploit|\betf\b.{0,30}(approv|reject|approuv|rejet)|invasion|declares war|d[ée]clare la guerre|nuclear strike|frappe nucl"


class News:
    def __init__(self, session_factory):
        self._session_factory = session_factory
        self.items = []
        self.seen = set()
        self.last_refresh = 0
        self.status = "en attente"

    async def run(self, on_new):
        session = self._session_factory()
        while True:
            await self.refresh(session, on_new)
            await asyncio.sleep(config.NEWS_REFRESH_SEC)

    async def refresh(self, session, on_new=None):
        ok = 0
        new = []
        for source, url in FEEDS.items():
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15),
                                       headers={"User-Agent": "Mozilla/5.0 trading-sim"}) as r:
                    r.raise_for_status()
                    new += self.parse(await r.text(), source)
                    ok += 1
            except Exception as e:  # noqa: BLE001
                log.warning("Flux %s indisponible : %s", source, e)
        self.items = sorted(self.items + new, key=lambda x: x["ts"], reverse=True)[:300]
        self.last_refresh = time.time()
        self.status = f"{ok}/{len(FEEDS)} sources lues"
        if new and on_new:
            await on_new(new)

    def parse(self, xml_text, source):
        out = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return out
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = item.findtext("pubDate")
            if not title:
                continue
            key = hashlib.md5(re.sub(r"\W+", "", title.lower())[:80].encode()).hexdigest()
            if key in self.seen:
                continue
            self.seen.add(key)
            try:
                ts = parsedate_to_datetime(pub).timestamp() if pub else time.time()
            except (TypeError, ValueError):
                ts = time.time()
            if ts < time.time() - 3 * 86400:
                continue
            out.append(self.classify({"title": title, "link": link, "source": source, "ts": ts}))
        return out

    @staticmethod
    def classify(item):
        text = item["title"].lower()
        themes = [t for t, rx in THEMES.items() if re.search(rx, text)]
        if re.search(r"guerre mondiale|world war (i|ii|1|2)\b|anniversaire|commémor", text):
            themes = [t for t in themes if t != "géopolitique"]  # histoire, pas actualité
        assets = [a for a, rx in ASSET_WORDS.items() if re.search(rx, text)]
        # Géopolitique et banques centrales touchent les trois actifs (l'or en premier lieu).
        if any(t in themes for t in ("géopolitique", "banques centrales", "macro")):
            assets = sorted(set(assets) | set(config.SYMBOLS))
        high = bool(re.search(HIGH_IMPACT, text))
        item.update({"themes": themes, "assets": assets,
                     "impact": "fort" if high else ("moyen" if themes else "faible")})
        return item

    def recent_high_impact(self, asset, minutes):
        limit = time.time() - minutes * 60
        return [n for n in self.items if n["ts"] >= limit and n["impact"] == "fort" and asset in n["assets"]]

    def tension(self, hours=6):
        """Nombre de titres géopolitiques sur les dernières heures (indicateur d'ambiance, pas un signal)."""
        limit = time.time() - hours * 3600
        return sum(1 for n in self.items if n["ts"] >= limit and "géopolitique" in n["themes"])

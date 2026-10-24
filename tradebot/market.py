"""Données de marché Binance : historique (REST) + flux temps réel (WebSocket),
avec repli automatique sur une interrogation toutes les 2 secondes."""
import asyncio
import json
import logging
import time

import aiohttp

from . import config

log = logging.getLogger("market")
T15 = aiohttp.ClientTimeout(total=15)
TF_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


class Market:
    def __init__(self, on_tick, on_close):
        self.on_tick = on_tick          # async (name, price, ts_ms)
        self.on_close = on_close        # async (name, tf)
        self.candles = {n: {tf: [] for tf in config.TIMEFRAMES} for n in config.SYMBOLS}
        self.prices = {}
        self.day_open = {}
        self.feed = "démarrage"
        self.last_tick = 0.0
        self.session = None

    # ---------- historique ----------
    async def bootstrap(self):
        for name, pair in config.SYMBOLS.items():
            for tf in config.TIMEFRAMES:
                self.candles[name][tf] = await self._klines(pair, tf, config.HISTORY_BARS)
            last = self.candles[name][config.ENTRY_TF][-1]
            self.prices[name] = last["c"]
            self.day_open[name] = self.candles[name]["1d"][-1]["o"]
        log.info("Historique chargé")

    async def _klines(self, pair, tf, limit):
        url = f"{config.REST_URL}/api/v3/klines"
        async with self.session.get(url, params={"symbol": pair, "interval": tf, "limit": limit}, timeout=T15) as r:
            r.raise_for_status()
            rows = await r.json()
        now = time.time() * 1000
        return [
            {"t": k[0], "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]),
             "v": float(k[5]), "closed": k[6] < now}
            for k in rows
        ]

    def closed(self, name, tf):
        """Bougies clôturées uniquement (les signaux ne regardent jamais une bougie en cours)."""
        return [c for c in self.candles[name][tf] if c["closed"]]

    # ---------- mise à jour d'une bougie ----------
    async def _update_candle(self, name, tf, k):
        series = self.candles[name][tf]
        bar = {"t": k["t"], "o": float(k["o"]), "h": float(k["h"]), "l": float(k["l"]),
               "c": float(k["c"]), "v": float(k["v"]), "closed": bool(k["x"])}
        if series and bar["t"] < series[-1]["t"]:
            # bougie plus ancienne (repli REST) : simple correction, sans événement
            for i in range(len(series) - 1, max(len(series) - 5, -1), -1):
                if series[i]["t"] == bar["t"]:
                    series[i] = {**bar, "closed": True}
                    break
            return
        if series and series[-1]["t"] == bar["t"]:
            was_closed = series[-1]["closed"]
            series[-1] = bar
        else:
            # bougie précédente éventuellement non marquée clôturée (repli REST)
            if series and not series[-1]["closed"]:
                series[-1]["closed"] = True
                await self.on_close(name, tf)
            series.append(bar)
            was_closed = False
            del series[:-config.HISTORY_BARS]
        if tf == "1d":
            self.day_open[name] = bar["o"]
        if bar["closed"] and not was_closed:
            await self.on_close(name, tf)

    # ---------- flux temps réel ----------
    async def run(self):
        self.session = aiohttp.ClientSession(trust_env=True)
        while True:
            try:
                await self.bootstrap()
                break
            except Exception as e:  # noqa: BLE001
                self.feed = "Binance injoignable, nouvel essai dans 15 s"
                log.warning("Chargement de l'historique impossible : %s", e)
                await asyncio.sleep(15)
        while True:
            try:
                await self._websocket()
            except Exception as e:  # noqa: BLE001
                log.warning("Flux temps réel indisponible (%s) : repli REST 60 s", e)
            self.feed = "REST (toutes les 2 s)"
            await self._poll(duration=60)

    async def _websocket(self):
        names = {pair.lower(): name for name, pair in config.SYMBOLS.items()}
        streams = []
        for pair in names:
            streams.append(f"{pair}@aggTrade")
            streams += [f"{pair}@kline_{tf}" for tf in config.TIMEFRAMES]
        url = f"{config.WS_URL}?streams={'/'.join(streams)}"
        async with self.session.ws_connect(url, heartbeat=20) as ws:
            self.feed = "temps réel (WebSocket)"
            log.info("Flux temps réel connecté")
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    break
                data = json.loads(msg.data)
                stream, d = data.get("stream", ""), data.get("data", {})
                name = names.get(stream.split("@")[0])
                if not name:
                    continue
                if "@aggTrade" in stream:
                    await self._tick(name, float(d["p"]), d["T"])
                elif "@kline_" in stream:
                    await self._update_candle(name, d["k"]["i"], d["k"])
        raise ConnectionError("connexion fermée")

    async def _poll(self, duration):
        end = time.time() + duration
        last_k = 0.0
        while time.time() < end:
            try:
                pairs = json.dumps(list(config.SYMBOLS.values()), separators=(",", ":"))
                async with self.session.get(f"{config.REST_URL}/api/v3/ticker/price",
                                            params={"symbols": pairs}, timeout=T15) as r:
                    rows = {x["symbol"]: float(x["price"]) for x in await r.json()}
                now = time.time() * 1000
                for name, pair in config.SYMBOLS.items():
                    if pair in rows:
                        await self._tick(name, rows[pair], now)
                if time.time() - last_k > 30:
                    last_k = time.time()
                    for name, pair in config.SYMBOLS.items():
                        for tf in config.TIMEFRAMES:
                            for k in await self._klines(pair, tf, 2):
                                await self._update_candle(name, tf, {**k, "x": k["closed"]})
            except Exception as e:  # noqa: BLE001
                log.warning("Interrogation REST échouée : %s", e)
            await asyncio.sleep(config.POLL_FALLBACK_SEC)

    async def _tick(self, name, price, ts):
        self.prices[name] = price
        self.last_tick = time.time()
        await self.on_tick(name, price, ts)

"""Point d'entrée : flux de marché + stratégie + courtier simulé + actualités + site en direct.
Lancer avec :  python -m tradebot.app"""
import asyncio
import base64
import json
import logging
import time
from pathlib import Path

import aiohttp
from aiohttp import web

from . import config, strategy
from .broker import PaperBroker
from .market import Market
from .news import News

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("app")
STATIC = Path(__file__).resolve().parent / "static"


class Bot:
    def __init__(self):
        self.broker = PaperBroker()
        self.market = Market(self.on_tick, self.on_close)
        self.news = News(lambda: self.http)
        self.http = None
        self.snapshots = {}
        self.clients = set()
        self.started = time.time()

    # ---------- marché ----------
    async def on_tick(self, name, price, ts):
        self.broker.on_price(name, price)

    async def on_close(self, name, tf):
        if tf != config.ENTRY_TF:
            return
        snap = strategy.analyze(self.market, name)
        self.snapshots[name] = snap
        sig, why = strategy.signal(snap)
        if sig is None:
            self.broker.log(name, "pas de trade", why)
            return
        hot = self.news.recent_high_impact(name, config.NEWS_PAUSE_MIN)
        if hot:
            self.broker.log(name, "ignoré", f"signal {sig['side']} mis en pause : actualité à fort impact "
                                            f"il y a moins de {config.NEWS_PAUSE_MIN} min (« {hot[0]['title'][:90]} »)")
            return
        self.broker.try_open(name, sig, self.market.prices)

    async def on_news(self, items):
        strong = [n for n in items if n["impact"] == "fort"]
        for n in strong[:5]:
            self.broker.events.append({"type": "news_alert", "title": n["title"], "assets": n["assets"]})
        self.broker.events.append({"type": "news"})

    # ---------- état pour le site ----------
    def state(self):
        p = self.market.prices
        open_trades = []
        for t in self.broker.open.values():
            price = p.get(t["asset"])
            sign = 1 if t["side"] == "long" else -1
            u = sign * (price - t["entry"]) * t["qty"] if price else 0
            open_trades.append({**t, "price": price, "unrealized": u,
                                "r_now": (u + t["realized"]) / t["risk_cash"] if t["risk_cash"] else 0})
        assets = {}
        for name in config.SYMBOLS:
            snap = self.snapshots.get(name)
            assets[name] = {
                "price": p.get(name),
                "day_change_pct": (p[name] / self.market.day_open[name] - 1) * 100
                if name in p and self.market.day_open.get(name) else None,
                "analysis": {k: v for k, v in snap.items() if k not in ("hh20", "ll20", "swing_low", "swing_high")} if snap else None,
                "levels": {"hh20": snap["hh20"], "ll20": snap["ll20"]} if snap else None,
                "news_pause": bool(self.news.recent_high_impact(name, config.NEWS_PAUSE_MIN)),
            }
        return {
            "server_time": time.time(),
            "uptime_s": time.time() - self.started,
            "feed": self.market.feed,
            "last_tick_age_s": time.time() - self.market.last_tick if self.market.last_tick else None,
            "assets": assets,
            "open": open_trades,
            "closed": self.broker.closed[-100:][::-1],
            "journal": self.broker.journal[-150:][::-1],
            "stats": self.broker.stats(p),
            "equity_curve": self.broker.equity_curve[-2000:],
            "news": self.news.items[:80],
            "news_status": self.news.status,
            "tension_6h": self.news.tension(),
            "settings": {
                "capital": config.START_CAPITAL, "risk_pct": config.RISK_PER_TRADE_PCT,
                "fee_pct": config.FEE_PCT, "slippage_bps": config.SLIPPAGE_BPS,
                "t1_r": config.TARGET1_R, "t2_r": config.TARGET2_R, "entry_tf": config.ENTRY_TF,
                "daily_loss_pct": config.DAILY_LOSS_LIMIT_PCT, "news_pause_min": config.NEWS_PAUSE_MIN,
            },
        }

    # ---------- diffusion en direct ----------
    async def broadcaster(self):
        while True:
            await asyncio.sleep(1)
            if not self.clients:
                self.broker.events.clear()
                continue
            msgs = [{"type": "prices", "prices": self.market.prices, "feed": self.market.feed,
                     "equity": self.broker.equity(self.market.prices),
                     "unrealized": self.broker.unrealized(self.market.prices)}]
            msgs += self.broker.events
            self.broker.events = []
            for q in list(self.clients):
                for m in msgs:
                    if q.qsize() < 200:
                        q.put_nowait(m)

    async def equity_recorder(self):
        while True:
            await asyncio.sleep(900)
            if self.market.prices:
                self.broker.record_equity(self.market.prices)

    async def initial_analysis(self):
        """Au démarrage : photo de chaque actif sans ouvrir de trade (on attend la prochaine clôture)."""
        while not all(self.market.candles[n][config.ENTRY_TF] for n in config.SYMBOLS):
            await asyncio.sleep(1)
        for name in config.SYMBOLS:
            self.snapshots[name] = strategy.analyze(self.market, name)
        self.broker.record_equity(self.market.prices)


# ---------- serveur web ----------
def make_app(bot):
    @web.middleware
    async def auth(request, handler):
        if config.DASH_PASSWORD:
            hdr = request.headers.get("Authorization", "")
            ok = False
            if hdr.startswith("Basic "):
                try:
                    ok = base64.b64decode(hdr[6:]).decode().split(":", 1)[1] == config.DASH_PASSWORD
                except Exception:  # noqa: BLE001
                    ok = False
            if not ok:
                return web.Response(status=401, headers={"WWW-Authenticate": 'Basic realm="trading-sim"'})
        return await handler(request)

    async def index(_):
        return web.FileResponse(STATIC / "index.html")

    async def state(_):
        return web.json_response(bot.state(), dumps=lambda o: json.dumps(o, default=str))

    async def stream(request):
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache",
                                           "X-Accel-Buffering": "no"})
        await resp.prepare(request)
        q = asyncio.Queue()
        bot.clients.add(q)
        try:
            while True:
                try:
                    m = await asyncio.wait_for(q.get(), timeout=15)
                    await resp.write(f"data: {json.dumps(m, default=str)}\n\n".encode())
                except asyncio.TimeoutError:
                    await resp.write(b": ping\n\n")
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            bot.clients.discard(q)
        return resp

    async def health(_):
        return web.json_response({"ok": True, "feed": bot.market.feed})

    app = web.Application(middlewares=[auth])
    app.add_routes([web.get("/", index), web.get("/api/state", state),
                    web.get("/api/stream", stream), web.get("/health", health)])
    return app


async def main():
    bot = Bot()
    bot.http = aiohttp.ClientSession(trust_env=True)
    runner = web.AppRunner(make_app(bot))
    await runner.setup()
    await web.TCPSite(runner, config.HOST, config.PORT).start()
    log.info("Site disponible sur http://%s:%s", config.HOST, config.PORT)
    await asyncio.gather(
        bot.market.run(),
        bot.news.run(bot.on_news),
        bot.broadcaster(),
        bot.equity_recorder(),
        bot.initial_analysis(),
    )


if __name__ == "__main__":
    asyncio.run(main())

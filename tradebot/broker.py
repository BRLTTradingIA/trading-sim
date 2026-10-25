"""Courtier simulé (paper trading) : aucun ordre réel n'est jamais envoyé.
Les stops et objectifs sont vérifiés à chaque tick de prix."""
import json
import time
import uuid
from datetime import datetime, timezone

from . import config
from .fmt import num

STATE_FILE = config.DATA_DIR / "state.json"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PaperBroker:
    def __init__(self):
        self.cash = config.START_CAPITAL
        self.open = {}          # id -> trade
        self.closed = []
        self.journal = []       # décisions (signaux pris ou ignorés, avec raison)
        self.equity_curve = []
        self.events = []        # file d'événements à pousser au site
        self._load()

    # ---------- persistance ----------
    def _load(self):
        if STATE_FILE.exists():
            s = json.loads(STATE_FILE.read_text())
            self.cash = s["cash"]
            self.open = s["open"]
            self.closed = s["closed"]
            self.journal = s["journal"]
            self.equity_curve = s["equity_curve"]

    def save(self):
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "cash": self.cash, "open": self.open, "closed": self.closed[-500:],
            "journal": self.journal[-500:], "equity_curve": self.equity_curve[-3000:],
        }))
        tmp.replace(STATE_FILE)

    # ---------- calculs ----------
    @staticmethod
    def _fill(price, side, opening):
        slip = price * config.SLIPPAGE_BPS / 10_000
        buying = (side == "long") == opening
        return price + slip if buying else price - slip

    def unrealized(self, prices):
        total = 0.0
        for t in self.open.values():
            p = prices.get(t["asset"])
            if p is not None:
                sign = 1 if t["side"] == "long" else -1
                total += sign * (p - t["entry"]) * t["qty"]
        return total

    def equity(self, prices):
        return self.cash + self.unrealized(prices)

    def today_realized(self):
        day = _now()[:10]
        return sum(t["pnl"] for t in self.closed if t["closed_at"][:10] == day)

    def log(self, asset, decision, detail):
        entry = {"time": _now(), "asset": asset, "decision": decision, "detail": detail}
        self.journal.append(entry)
        self.events.append({"type": "journal", **entry})

    # ---------- ouverture ----------
    def try_open(self, asset, sig, prices):
        if any(t["asset"] == asset for t in self.open.values()):
            self.log(asset, "ignoré", "un trade est déjà ouvert sur cet actif")
            return
        if len(self.open) >= config.MAX_OPEN_TRADES:
            self.log(asset, "ignoré", f"déjà {config.MAX_OPEN_TRADES} trades ouverts (limite d'exposition)")
            return
        eq = self.equity(prices)
        if self.today_realized() <= -eq * config.DAILY_LOSS_LIMIT_PCT / 100:
            self.log(asset, "ignoré", f"limite de perte journalière ({config.DAILY_LOSS_LIMIT_PCT} %) atteinte")
            return
        entry = self._fill(sig["entry"], sig["side"], True)
        risk_unit = abs(entry - sig["stop"])
        if risk_unit <= 0:
            return
        # coût aller-retour estimé par unité (frais des deux côtés + glissement de sortie)
        cost_unit = entry * (2 * config.FEE_PCT / 100 + config.SLIPPAGE_BPS / 10_000)
        share = cost_unit / risk_unit
        if share > config.MAX_COST_SHARE:
            self.log(asset, "ignoré", f"stop trop serré : les frais coûteraient {share * 100:.0f} % de l'écart "
                                      f"entrée-stop (max {config.MAX_COST_SHARE * 100:.0f} %)")
            return
        risk_cash = eq * config.RISK_PER_TRADE_PCT / 100
        qty = risk_cash / (risk_unit + cost_unit)   # perte au stop, frais compris = 1 % du capital
        used = sum(t["entry"] * t["qty"] for t in self.open.values())
        max_qty = max(eq * config.MAX_LEVERAGE - used, 0) / entry
        capped = qty > max_qty
        qty = min(qty, max_qty)
        if qty * entry < 50:
            self.log(asset, "ignoré", "capital disponible insuffisant (déjà engagé sur d'autres trades)")
            return
        fee = entry * qty * config.FEE_PCT / 100
        self.cash -= fee
        tid = uuid.uuid4().hex[:8]
        self.open[tid] = {
            "id": tid, "asset": asset, "side": sig["side"], "entry": entry, "stop": sig["stop"],
            "initial_stop": sig["stop"], "t1": sig["t1"], "t2": sig["t2"], "qty": qty,
            "initial_qty": qty, "risk_cash": (risk_unit + cost_unit) * qty, "fees": fee, "realized": -fee,
            "t1_hit": False, "opened_at": _now(), "reasons": sig["reasons"],
        }
        note = " (taille plafonnée : pas d'effet de levier)" if capped else ""
        self.log(asset, "ouvert", f"{sig['side']} à {num(entry)}, stop {num(sig['stop'])}, "
                                  f"objectifs {num(sig['t1'])} / {num(sig['t2'])}{note}")
        self.events.append({"type": "trades"})
        self.save()

    # ---------- suivi à chaque tick ----------
    def on_price(self, asset, price):
        changed = False
        for tid, t in list(self.open.items()):
            if t["asset"] != asset:
                continue
            long_ = t["side"] == "long"
            hit_stop = price <= t["stop"] if long_ else price >= t["stop"]
            hit_t1 = not t["t1_hit"] and (price >= t["t1"] if long_ else price <= t["t1"])
            hit_t2 = price >= t["t2"] if long_ else price <= t["t2"]
            if hit_stop:
                self._close(tid, t["stop"], t["qty"], "stop" if not t["t1_hit"] else "stop au prix d'entrée")
                changed = True
            elif hit_t2:
                self._close(tid, t["t2"], t["qty"], "objectif 2")
                changed = True
            elif hit_t1:
                half = t["qty"] / 2
                self._partial(t, t["t1"], half)
                t["t1_hit"] = True
                t["stop"] = t["entry"]
                self.log(asset, "objectif 1", f"moitié clôturée à {num(t['t1'])}, stop remonté au prix d'entrée")
                changed = True
        if changed:
            self.events.append({"type": "trades"})
            self.save()

    def _pnl(self, t, exit_price, qty):
        sign = 1 if t["side"] == "long" else -1
        fill = self._fill(exit_price, t["side"], False)
        fee = fill * qty * config.FEE_PCT / 100
        return sign * (fill - t["entry"]) * qty - fee, fee, fill

    def _partial(self, t, price, qty):
        pnl, fee, _ = self._pnl(t, price, qty)
        self.cash += pnl  # pnl déjà net des frais de sortie
        t["realized"] += pnl
        t["fees"] += fee
        t["qty"] -= qty

    def _close(self, tid, price, qty, reason):
        t = self.open.pop(tid)
        pnl, fee, fill = self._pnl(t, price, qty)
        self.cash += pnl
        t["realized"] += pnl
        t["fees"] += fee
        t.update({
            "exit": fill, "closed_at": _now(), "exit_reason": reason,
            "pnl": t["realized"], "r_multiple": t["realized"] / t["risk_cash"] if t["risk_cash"] else 0,
        })
        self.closed.append(t)
        self.log(t["asset"], "clôturé", f"{reason} à {num(fill)}, résultat {'+' if (t['realized']) >= 0 else ''}{num(t['realized'])} $ "
                                        f"({t['r_multiple']:+.2f} R)")

    # ---------- statistiques ----------
    def stats(self, prices):
        pnls = [t["pnl"] for t in self.closed]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        eq = self.equity(prices)
        peak, mdd = config.START_CAPITAL, 0.0
        for point in self.equity_curve:
            peak = max(peak, point["eq"])
            mdd = max(mdd, (peak - point["eq"]) / peak * 100)
        return {
            "equity": eq,
            "start": config.START_CAPITAL,
            "return_pct": (eq / config.START_CAPITAL - 1) * 100,
            "n_closed": len(pnls),
            "n_open": len(self.open),
            "win_rate": len(wins) / len(pnls) * 100 if pnls else None,
            "profit_factor": sum(wins) / -sum(losses) if losses and sum(losses) < 0 else None,
            "avg_r": sum(t["r_multiple"] for t in self.closed) / len(pnls) if pnls else None,
            "fees": sum(t["fees"] for t in self.closed) + sum(t["fees"] for t in self.open.values()),
            "max_dd": mdd,
            "unrealized": self.unrealized(prices),
        }

    def record_equity(self, prices):
        self.equity_curve.append({"t": int(time.time()), "eq": round(self.equity(prices), 2)})
        self.save()

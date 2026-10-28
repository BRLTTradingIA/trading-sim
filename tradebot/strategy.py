"""Stratégie « suivi de tendance sur repli », lecture du haut vers le bas :
1. Tendance de fond en 1d et 4h  -> on ne trade que dans le sens des deux.
2. Déclencheur en 1h : reprise du RSI après un repli, ou cassure du plus haut/bas de 20 bougies.
3. Stop sous le dernier creux (ou au-dessus du dernier sommet), borné entre 1 et 3 ATR.
Aucune prédiction : des règles fixes, testables, et chaque décision est expliquée."""
from . import config
from .fmt import num
from .indicators import atr, ema, rsi, sma


def _trend(bars, fast=50, slow=200):
    closes = [b["c"] for b in bars]
    if len(closes) < slow:
        return "inconnue", "historique insuffisant"
    ef, es = ema(closes, fast)[-1], ema(closes, slow)[-1]
    c = closes[-1]
    if c > ef > es:
        return "haussière", f"clôture {num(c)} > EMA{fast} {num(ef)} > EMA{slow} {num(es)}"
    if c < ef < es:
        return "baissière", f"clôture {num(c)} < EMA{fast} {num(ef)} < EMA{slow} {num(es)}"
    return "latérale", "prix et moyennes non alignés"


def analyze(market, name, entry="1h", trends=("1d", "4h")):
    """Photo de l'actif (même sans signal). entry = unité de temps du déclencheur,
    trends = les deux unités de temps qui donnent le biais."""
    h1 = market.closed(name, entry)
    if len(h1) < 60:
        return None
    closes = [b["c"] for b in h1]
    highs = [b["h"] for b in h1]
    lows = [b["l"] for b in h1]
    vols = [b["v"] for b in h1]
    r = rsi(closes)
    a = atr(highs, lows, closes)
    vavg = sma(vols, 20)[-1] or 1
    hi_tf, mid_tf = trends
    t1d, why1d = _trend(market.closed(name, hi_tf))
    t4h, why4h = _trend(market.closed(name, mid_tf))
    t1h, why1h = _trend(h1, 20, 50)
    if t1d == t4h == "haussière":
        bias = "acheteur"
    elif t1d == t4h == "baissière":
        bias = "vendeur"
    else:
        bias = "neutre"
    return {
        "tfs": [hi_tf, mid_tf, entry],
        "trend": {hi_tf: t1d, mid_tf: t4h, entry: t1h},
        "trend_why": {hi_tf: why1d, mid_tf: why4h, entry: why1h},
        "bias": bias,
        "rsi": round(r[-1], 1),
        "rsi_prev": round(r[-2], 1),
        "atr": a[-1],
        "atr_pct": round(a[-1] / closes[-1] * 100, 2),
        "vol_ratio": round(vols[-1] / vavg, 2),
        "hh20": max(highs[-21:-1]),
        "ll20": min(lows[-21:-1]),
        "swing_low": min(lows[-6:]),
        "swing_high": max(highs[-6:]),
        "close": closes[-1],
        "bar_time": h1[-1]["t"],
    }


def signal(snap):
    """Renvoie (signal ou None, explication)."""
    if snap is None:
        return None, "pas assez de données"
    bias = snap["bias"]
    if bias == "neutre":
        ta, tb, _ = snap["tfs"]
        return None, (f"pas de trade : tendances {ta} ({snap['trend'][ta]}) et {tb} "
                      f"({snap['trend'][tb]}) pas alignées")
    c, a = snap["close"], snap["atr"]
    ta, tb, e = snap["tfs"]
    reasons = [f"tendance {ta} {snap['trend'][ta]}", f"tendance {tb} {snap['trend'][tb]}"]
    if bias == "acheteur":
        pullback = snap["rsi_prev"] < 40 <= snap["rsi"]
        breakout = c > snap["hh20"]
        if not (pullback or breakout):
            return None, f"biais acheteur, mais pas de déclencheur {e} (RSI {snap['rsi']}, plus haut 20 = {num(snap['hh20'])})"
        reasons.append("RSI repasse au-dessus de 40 après un repli" if pullback else f"cassure du plus haut des 20 dernières bougies {e}")
        raw_stop = snap["swing_low"] - 0.2 * a
        dist = min(max(c - raw_stop, config.MIN_STOP_ATR * a), config.MAX_STOP_ATR * a)
        side, stop = "long", c - dist
    else:
        pullback = snap["rsi_prev"] > 60 >= snap["rsi"]
        breakout = c < snap["ll20"]
        if not (pullback or breakout):
            return None, f"biais vendeur, mais pas de déclencheur {e} (RSI {snap['rsi']}, plus bas 20 = {num(snap['ll20'])})"
        reasons.append("RSI repasse sous 60 après un rebond" if pullback else f"cassure du plus bas des 20 dernières bougies {e}")
        raw_stop = snap["swing_high"] + 0.2 * a
        dist = min(max(raw_stop - c, config.MIN_STOP_ATR * a), config.MAX_STOP_ATR * a)
        side, stop = "short", c + dist
    if snap["vol_ratio"] < 0.5:
        return None, f"déclencheur présent mais volume trop faible ({snap['vol_ratio']}× la moyenne)"
    sign = 1 if side == "long" else -1
    return {
        "side": side,
        "entry": c,
        "stop": stop,
        "t1": c + sign * dist * config.TARGET1_R,
        "t2": c + sign * dist * config.TARGET2_R,
        "reasons": reasons + [f"stop à {dist / a:.1f} ATR", f"volume {snap['vol_ratio']}× la moyenne"],
    }, "signal"

"""Indicateurs techniques simples (sans dépendance externe)."""


def ema(values, n):
    if len(values) < n:
        return [None] * len(values)
    k = 2 / (n + 1)
    out = [None] * (n - 1)
    prev = sum(values[:n]) / n
    out.append(prev)
    for v in values[n:]:
        prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


def sma(values, n):
    out = []
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        out.append(s / n if i >= n - 1 else None)
    return out


def rsi(closes, n=14):
    """RSI de Wilder."""
    if len(closes) <= n:
        return [None] * len(closes)
    out = [None] * n
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n
    out.append(100 - 100 / (1 + ag / al) if al else 100.0)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out.append(100 - 100 / (1 + ag / al) if al else 100.0)
    return out


def atr(highs, lows, closes, n=14):
    trs = []
    for i in range(len(closes)):
        if i == 0:
            trs.append(highs[i] - lows[i])
        else:
            trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    if len(trs) < n:
        return [None] * len(trs)
    out = [None] * (n - 1)
    prev = sum(trs[:n]) / n
    out.append(prev)
    for tr in trs[n:]:
        prev = (prev * (n - 1) + tr) / n
        out.append(prev)
    return out

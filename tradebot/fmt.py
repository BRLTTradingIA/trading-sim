def num(x, d=None):
    """Nombre au format français (80 662,01 ; 0,1234 pour les petits prix)."""
    if d is None:
        d = 2 if abs(x) >= 10 else 4 if abs(x) >= 0.1 else 6
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")

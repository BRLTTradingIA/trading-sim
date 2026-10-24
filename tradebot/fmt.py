def num(x, d=2):
    """Nombre au format français : 80 662,01"""
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")

"""Ritocchi di layout puri (senza gi): i vicini seguono il ridimensionamento."""

from __future__ import annotations

from .models import MonitorConfig, PositionMode

# Tolleranza in pixel logici per considerare due bordi a contatto
_TOUCH_TOL = 1


def _movable(m: MonitorConfig) -> bool:
    return m.enabled and m.position_mode == PositionMode.EXPLICIT


def _overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    return a_start < b_end and b_start < a_end


def _followers(
    monitors: list[MonitorConfig], index: int, vertical_axis: bool,
    old_size: float, old_cross: float,
) -> dict[int, int]:
    """Mappa ogni monitor che segue il bordo destro (o basso) di *index*
    all'indice del vicino di primo livello da cui dipende.

    Usa la geometria vecchia della sorgente (bordo e estensione trasversale);
    i vicini non sono ancora stati spostati.  Poi propaga a catena.
    """
    def span(m: MonitorConfig) -> tuple[float, float, float, float]:
        # (inizio lungo l'asse, fine lungo l'asse, inizio trasversale, fine trasversale)
        if vertical_axis:
            return m.y, m.y + m.logical_height, m.x, m.x + m.logical_width
        return m.x, m.x + m.logical_width, m.y, m.y + m.logical_height

    start, _end, c0, _c1 = span(monitors[index])
    # (bordo di contatto, intervallo trasversale, radice) della sorgente
    frontier: list[tuple[float, float, float, int | None]] = [
        (start + old_size, c0, c0 + old_cross, None)
    ]
    roots: dict[int, int] = {}
    while frontier:
        edge, f0, f1, root = frontier.pop()
        for i, m in enumerate(monitors):
            if i == index or i in roots or not _movable(m):
                continue
            s, e, t0, t1 = span(m)
            if abs(s - edge) <= _TOUCH_TOL and _overlap(f0, f1, t0, t1):
                r = i if root is None else root
                roots[i] = r
                frontier.append((e, t0, t1, r))
    return roots


def _shift(
    monitors: list[MonitorConfig], roots: dict[int, int],
    start: float, new_size: float, vertical_axis: bool,
) -> None:
    """Posiziona ogni vicino di primo livello dal bordo di arrivo.

    L'errore resta sotto 0.5 px a prescindere dal numero di passi; la catena
    di ogni vicino trasla dello stesso delta.
    """
    edge = start + new_size
    attr = "y" if vertical_axis else "x"
    deltas = {r: round(edge) - getattr(monitors[r], attr) for r in set(roots.values())}
    for i, r in roots.items():
        setattr(monitors[i], attr, getattr(monitors[i], attr) + deltas[r])


def follow_resize(
    monitors: list[MonitorConfig], index: int, old_width: float, old_height: float,
) -> None:
    """Sposta i vicini a contatto del monitor *index* dopo un cambio di taglia.

    ``old_width``/``old_height`` sono le dimensioni logiche precedenti, usate
    per bordo e sovrapposizione.  I vicini di primo livello vanno al bordo
    nuovo arrotondato (nessun accumulo su passi piccoli), le catene seguono.
    """
    if not (0 <= index < len(monitors)):
        return
    m = monitors[index]
    if not m.enabled:
        return
    changed_x = round(m.logical_width - old_width) != 0
    changed_y = round(m.logical_height - old_height) != 0
    # Entrambi gli insiemi dalla geometria vecchia, poi si applica
    right = _followers(monitors, index, False, old_width, old_height) if changed_x else {}
    below = _followers(monitors, index, True, old_height, old_width) if changed_y else {}
    _shift(monitors, right, m.x, m.logical_width, False)
    _shift(monitors, below, m.y, m.logical_height, True)

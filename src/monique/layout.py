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
    old_size: float,
) -> set[int]:
    """Indici dei monitor che seguono il bordo destro (o basso) di *index*.

    Usa solo la geometria attuale dei vicini (mai ancora spostati) e parte
    dal bordo vecchio del monitor ridimensionato; poi propaga a catena.
    """
    def span(m: MonitorConfig) -> tuple[float, float, float, float]:
        # (inizio lungo l'asse, fine lungo l'asse, inizio trasversale, fine trasversale)
        if vertical_axis:
            return m.y, m.y + m.logical_height, m.x, m.x + m.logical_width
        return m.x, m.x + m.logical_width, m.y, m.y + m.logical_height

    src = monitors[index]
    start, _end, c0, c1 = span(src)
    # (bordo di contatto, intervallo trasversale) della sorgente
    frontier = [(start + old_size, c0, c1)]
    moved: set[int] = set()
    while frontier:
        edge, f0, f1 = frontier.pop()
        for i, m in enumerate(monitors):
            if i == index or i in moved or not _movable(m):
                continue
            s, e, t0, t1 = span(m)
            if abs(s - edge) <= _TOUCH_TOL and _overlap(f0, f1, t0, t1):
                moved.add(i)
                frontier.append((e, t0, t1))
    return moved


def follow_resize(
    monitors: list[MonitorConfig], index: int, old_width: float, old_height: float,
) -> None:
    """Sposta i vicini a contatto del monitor *index* dopo un cambio di taglia.

    ``old_width``/``old_height`` sono le dimensioni logiche precedenti.  Il
    delta è calcolato una sola volta sul monitor ridimensionato, così le
    posizioni restano intere e le catene non accumulano arrotondamenti.
    """
    if not (0 <= index < len(monitors)):
        return
    m = monitors[index]
    if not m.enabled:
        return
    dx = round(m.logical_width - old_width)
    dy = round(m.logical_height - old_height)
    # Entrambi gli insiemi dalla geometria vecchia, poi si applica
    right = _followers(monitors, index, False, old_width) if dx else set()
    below = _followers(monitors, index, True, old_height) if dy else set()
    for i in right:
        monitors[i].x += dx
    for i in below:
        monitors[i].y += dy

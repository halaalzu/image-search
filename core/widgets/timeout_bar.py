from core.widgets.abstractwidget import AbstractWidget
from core.constants import Group as G
from pyglet.gl import GL_QUADS, GL_LINES


class TimeoutBar(AbstractWidget):
    """Horizontal bar that depletes left-to-right to show a countdown deadline.

    Fraction 1.0 = full time remaining.  Fraction 0.0 = deadline reached.
    Fill colour interpolates from full_color (green) to low_color (red).
    The bar is hidden by default; call show()/hide() to control visibility.
    """

    def __init__(self, name, container, win,
                 full_color=(60, 200, 60, 255),
                 low_color=(220, 60, 60, 255),
                 back_color=(40, 40, 40, 200),
                 draw_order=30):
        super().__init__(name, container, win)
        self.full_color = full_color
        self.low_color = low_color
        self._frac = 1.0

        verts = list(self.vertice_border(self.container))
        self.add_vertex('background', 4, GL_QUADS, G(self.m_draw + draw_order),
                        ('v2f/static', verts),
                        ('c4B/static', list(back_color * 4)))
        self.add_vertex('fill', 4, GL_QUADS, G(self.m_draw + draw_order + 1),
                        ('v2f/dynamic', verts),
                        ('c4B/dynamic', list(full_color * 4)))

    def set_fraction(self, frac):
        if 'fill' not in self.on_batch:
            return
        frac = max(0.0, min(1.0, frac))
        self._frac = frac
        l = self.container.l
        b = self.container.b
        r = l + self.container.w
        t = b + self.container.h
        r_fill = l + (r - l) * frac
        self.on_batch['fill'].vertices[:] = [l, b, r_fill, b, r_fill, t, l, t]
        color = tuple(
            int(self.full_color[i] + (self.low_color[i] - self.full_color[i]) * (1.0 - frac))
            for i in range(4)
        )
        self.on_batch['fill'].colors[:] = list(color * 4)


class AutomodeIndicator(AbstractWidget):
    """Small colored square at a fixed screen position.

    Green  when automation is active (auto=True).
    Dark-grey when automation is inactive (auto=False / manual).
    """

    def __init__(self, name, container, win,
                 color_on=(50, 210, 50, 255),
                 color_off=(90, 90, 90, 210),
                 border_color=(190, 190, 190, 255),
                 draw_order=50):
        super().__init__(name, container, win)
        self.color_on = color_on
        self.color_off = color_off

        verts = list(self.vertice_border(self.container))
        self.add_vertex('fill', 4, GL_QUADS, G(self.m_draw + draw_order),
                        ('v2f/static', verts),
                        ('c4B/dynamic', list(color_off * 4)))
        self.add_vertex('border', 8, GL_LINES, G(self.m_draw + draw_order + 1),
                        ('v2f/static', self.vertice_strip(verts)),
                        ('c4B/static', list(border_color * 8)))

    def set_active(self, is_active):
        if 'fill' not in self.on_batch:
            return
        color = self.color_on if is_active else self.color_off
        self.on_batch['fill'].colors[:] = list(color * 4)

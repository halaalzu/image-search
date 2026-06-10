# Copyright 2023, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

from core.widgets.abstractwidget import *
from pyglet.text import Label
from pyglet.gl import GL_QUADS, GL_LINES
from core.constants import FONT_SIZES as FONT_SIZES_DICT

class HealthBar(AbstractWidget):
    def __init__(self, name, container, win, max_health=100.0, min_health=0.0,
                 good_color=(0, 180, 0, 255), bad_color=(200, 30, 30, 255),
                 back_color=(35, 35, 35, 255), border_color=(0, 0, 0, 255),
                 text_color=(255, 255, 255, 255), label='HEALTH',
                 orientation='horizontal', label_font_key='SMALL', value_font_key='SMALL'):
        super().__init__(name, container, win)

        self.max_health = max_health
        self.min_health = min_health
        self._health = max_health
        self.good_color = good_color
        self.bad_color = bad_color
        self.back_color = back_color
        self.border_color = border_color
        self.text_color = text_color
        self.label_text = label
        self.orientation = orientation if orientation in ('horizontal', 'vertical') else 'horizontal'
        self.label_font_size = FONT_SIZES_DICT.get(label_font_key.upper(), F['SMALL'])
        self.value_font_size = FONT_SIZES_DICT.get(value_font_key.upper(), F['SMALL'])

        # Background with slight padding for border effect
        self.border_vertices = self.vertice_border(self.container)
        self.add_vertex('background', 4, GL_QUADS, G(self.m_draw + 1),
                        ('v2f/static', self.border_vertices),
                        ('c4B/static', self.back_color * 4))

        # Fill (dynamic) - will be updated based on health
        self.add_vertex('fill', 4, GL_QUADS, G(self.m_draw + 2),
                        ('v2f/dynamic', self.border_vertices),
                        ('c4B/dynamic', self.good_color * 4))

        # Border - bright white for visibility
        self.add_vertex('border', 8, GL_LINES, G(self.m_draw + 3),
                        ('v2f/static', self.vertice_strip(self.border_vertices)),
                        ('c4B/static', self.border_color * 8))

        container_top = self.container.b + self.container.h
        container_bottom = self.container.b
        container_left = self.container.l
        container_right = self.container.l + self.container.w

        if self.orientation == 'vertical':
            label_x = container_left + self.container.w / 2
            label_y = container_top - 2
            label_anchor_x, label_anchor_y = 'center', 'top'
            value_x = container_left + self.container.w / 2
            value_y = container_bottom + 4
            value_anchor_x, value_anchor_y = 'center', 'bottom'
        else:
            label_x = container_left + 4
            label_y = container_top - 2
            label_anchor_x, label_anchor_y = 'left', 'top'
            value_x = container_right - 4
            value_y = container_top - 2
            value_anchor_x, value_anchor_y = 'right', 'top'

        # Label - NOT DISPLAYED (keeping reference for compatibility)
        self.label_props = {
            'x': label_x, 'y': label_y,
            'anchor_x': label_anchor_x, 'anchor_y': label_anchor_y
        }
        # Skip creating label to hide bar names (SYSMON, NAV, COMMS)

        # Value label
        self.value_props = {
            'x': value_x, 'y': value_y,
            'anchor_x': value_anchor_x, 'anchor_y': value_anchor_y
        }
        self.vertex['value'] = Label(self._health_text(),
                                     font_size=self.value_font_size,
                                     x=value_x,
                                     y=value_y,
                                     anchor_x=value_anchor_x, anchor_y=value_anchor_y,
                                     color=self.text_color,
                                     group=G(self.m_draw + 4),
                                     font_name=self.font_name)

        # Update initial fill
        self._update_fill()

    def update_render_order(self):
        """Update vertex groups to use the current m_draw value. Call before show()."""
        # Rebuild vertex tuples with updated Group values
        self.vertex['background'] = (4, GL_QUADS, G(self.m_draw + 1),
                                     ('v2f/static', self.border_vertices),
                                     ('c4B/static', self.back_color * 4))
        self.vertex['fill'] = (4, GL_QUADS, G(self.m_draw + 2),
                               ('v2f/dynamic', self.border_vertices),
                               ('c4B/dynamic', self.good_color * 4))
        self.vertex['border'] = (8, GL_LINES, G(self.m_draw + 3),
                                 ('v2f/static', self.vertice_strip(self.border_vertices)),
                                 ('c4B/static', self.border_color * 8))
        # Recreate labels with new render groups
        # Label is NOT created (hiding SYSMON/NAV/COMMS)
        if 'value' in self.vertex:
            props = self.value_props
            self.vertex['value'] = Label(self._health_text(),
                                        font_size=self.value_font_size,
                                        x=props['x'],
                                        y=props['y'],
                                        anchor_x=props['anchor_x'],
                                        anchor_y=props['anchor_y'],
                                        color=self.text_color,
                                        group=G(self.m_draw + 4),
                                        font_name=self.font_name)

    def _health_text(self):
        from math import ceil
        return f"{ceil(self._health)}/{int(self.max_health)}"

    def _lerp_color(self, c0, c1, t):
        """Interpolate between two colors. t in [0,1]"""
        return tuple(int(c0[i] + (c1[i] - c0[i]) * t) for i in range(4))

    def _update_fill(self):
        """Update the fill bar geometry and color based on current health"""
        if 'fill' not in self.on_batch:
            return

        # Calculate fill fraction
        health_range = self.max_health - self.min_health
        if health_range <= 0:
            frac = 0.0
        else:
            frac = (self._health - self.min_health) / health_range
        frac = max(0.0, min(1.0, frac))

        # Interpolate color from bad to good based on health
        fill_color = self._lerp_color(self.bad_color, self.good_color, frac)

        l = self.container.l
        b = self.container.b
        r = self.container.l + self.container.w
        t = self.container.b + self.container.h

        if self.orientation == 'vertical':
            t_fill = b + (t - b) * frac
            self.on_batch['fill'].vertices[:] = (l, b, r, b, r, t_fill, l, t_fill)
        else:
            r_fill = l + (r - l) * frac
            self.on_batch['fill'].vertices[:] = (l, b, r_fill, b, r_fill, t, l, t)

        # Update fill color
        self.on_batch['fill'].colors[:] = fill_color * 4

        # Update value label
        if 'value' in self.vertex:
            self.vertex['value'].text = self._health_text()

    def set_health(self, health):
        """Set the health value and update the display"""
        health = max(self.min_health, min(self.max_health, health))
        if health == self._health:
            return
        self._health = health
        self._update_fill()
        self.logger.record_state(self.name, 'health', self._health)

    def get_health(self):
        """Get the current health value"""
        return self._health

    def add_health(self, delta):
        """Add (or subtract) health"""
        self.set_health(self._health + delta)


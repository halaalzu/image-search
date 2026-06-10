"""Minimal flash indicator plugin.

Draws a circle (≈100 px diameter by default) that starts black and turns
white when triggered from the scenario (e.g., ``0:06:00;flash;true``).
"""

from pyglet.gl import GL_POLYGON, GL_QUADS

from plugins.abstract import AbstractPlugin
from core.container import Container
from core.constants import COLORS as C, Group as G
from core.widgets import AbstractWidget


class _FlashCircle(AbstractWidget):
    """Simple circular widget with configurable fill and border colors."""

    def __init__(self, name, container, win, fill_color, draw_order=None):
        super().__init__(name, container, win)
        if draw_order is not None:
            self.m_draw = draw_order
        self._vertex_count = 0
        self._fill_color = fill_color

        vertices = self.vertice_circle(container.get_center(), container.w / 2, 60)
        self._vertex_count = len(vertices) // 2
        self.add_vertex(
            "fill",
            self._vertex_count,
            GL_POLYGON,
            G(self.m_draw),
            ("v2f/static", vertices),
            ("c4B/dynamic", fill_color * self._vertex_count),
        )
    def set_fill_color(self, color):
        if color == self._fill_color:
            return
        self._fill_color = color
        if "fill" in self.on_batch:
            self.on_batch["fill"].colors[:] = color * self._vertex_count
        self.logger.record_state(self.name, "fill_color", color)


class _FlashPanel(AbstractWidget):
    """Full-size rectangular background for the flash area."""

    def __init__(self, name, container, win, color, draw_order=None):
        super().__init__(name, container, win)
        if draw_order is not None:
            self.m_draw = draw_order
        self._color = color
        vertices = self.vertice_border(container)
        self.add_vertex(
            "panel",
            4,
            GL_QUADS,
            G(self.m_draw),
            ("v2f/static", vertices),
            ("c4B/dynamic", color * 4),
        )

    def set_color(self, color):
        if color == self._color:
            return
        self._color = color
        if "panel" in self.on_batch:
            self.on_batch["panel"].colors[:] = color * 4
        self.logger.record_state(self.name, "panel_color", color)


class Flash(AbstractPlugin):
    """Circle indicator that can be toggled via scenario events."""

    def __init__(self, taskplacement='bottomright', taskupdatetime=250):
        super().__init__(taskplacement, taskupdatetime)
        self.parameters.update(
            dict(
                diameter_px=50,
                active_color=C["WHITE"],
                inactive_color=(0, 0, 0, 255),  # Pure black for sensor detection
                panel_color=(0, 0, 0, 255),  # Pure black for sensor detection
                state=False,
            )
        )
        self._circle = None
        self._panel = None

    # ------------------------------------------------------------------ #
    # Widget lifecycle
    # ------------------------------------------------------------------ #
    def create_widgets(self):
        super().create_widgets()

        self._panel = self.add_widget(
            "panel",
            _FlashPanel,
            container=self.task_container,
            color=self.parameters["panel_color"],
            draw_order=self.m_draw,
        )

        size = min(
            self.parameters["diameter_px"],
            self.task_container.w,
            self.task_container.h,
        )
        cx, cy = self.task_container.get_center()
        circle_container = Container(
            f"{self.alias}_circle",
            cx - size / 2,
            cy - size / 2,
            size,
            size,
        )
        self._circle = self.add_widget(
            "circle",
            _FlashCircle,
            container=circle_container,
            fill_color=self._current_color(),
            draw_order=self.m_draw + 1,
        )

    def refresh_widgets(self):
        if self._panel is not None:
            self._panel.set_color(self.parameters["panel_color"])
        if self._circle is not None:
            self._circle.set_fill_color(self._current_color())
        return super().refresh_widgets()

    # ------------------------------------------------------------------ #
    # Scenario / public API
    # ------------------------------------------------------------------ #
    def true(self):
        """Scenario command: ``...;flash;true``."""
        self.set_state(True)

    def false(self):
        """Scenario command: ``...;flash;false``."""
        self.set_state(False)

    def toggle(self):
        self.set_state(not self.parameters["state"])

    def set_state(self, value):
        new_state = self._coerce_bool(value)
        if self.parameters["state"] == new_state:
            return
        self.parameters["state"] = new_state
        if self._circle is not None:
            self._circle.set_fill_color(self._current_color())

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _current_color(self):
        return (
            self.parameters["active_color"]
            if self.parameters["state"]
            else self.parameters["inactive_color"]
        )

    def _coerce_bool(self, value):
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "1", "yes", "on"):
                return True
            if lowered in ("false", "0", "no", "off"):
                return False
        return bool(value)


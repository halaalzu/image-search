# plugins/chrono.py
from time import gmtime, strftime
from plugins.abstract import AbstractPlugin
from core.widgets import Simpletext

class Chrono(AbstractPlugin):
    def __init__(self, taskplacement='topright', taskupdatetime=500):
        super().__init__(taskplacement, taskupdatetime)
        # label: "Elapsed" or "Remaining"
        # reverse: False => elapsed clock; True => countdown
        # totalseconds: only used when reverse=True
        self.parameters.update(dict(label="Elapsed", reverse=False, totalseconds=360))

    def create_widgets(self):
        super().create_widgets()
        # Keep it simple: same style as Scheduling (no anchor kwarg)
        # y is relative to the plugin container height
        self.add_widget('clock', Simpletext,
                        container=self.task_container,
                        text=self._text(),
                        y=0.08)

    def refresh_widgets(self):
        if super().refresh_widgets() == 0:
            return
        self.widgets[f'{self.alias}_clock'].set_text(self._text())

    def _text(self):
        t = int(self.scenario_time)
        if self.parameters['reverse']:
            t = max(0, int(self.parameters['totalseconds']) - t)
            return f"Remaining {strftime('%H:%M:%S', gmtime(t))}"
        return f"{self.parameters['label']} {strftime('%H:%M:%S', gmtime(t))}"

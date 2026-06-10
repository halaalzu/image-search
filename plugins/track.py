# Copyright 2023, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)



from math import sin, pi, ceil
from builtins import _
from pyglet.input import get_joysticks
from plugins.abstract import AbstractPlugin
from core.widgets import Reticle
from core.error import errors
from core.container import Container
from core.constants import Group as G, COLORS as C, FONT_SIZES as F, REPLAY_MODE
from core.logger import logger


class Track(AbstractPlugin):
    def __init__(self, taskplacement='topright', taskupdatetime=20, silent=False):
        super().__init__(taskplacement, taskupdatetime)

        new_par = dict(cursorcolor=C['BLACK'], cursorcoloroutside=C['RED'], automaticsolver=False,
                       displayautomationstate=True, targetproportion=0.25, joystickforce=1,
                       inverseaxis=False)
        self.parameters.update(new_par)


        self.automode_position = (0.35, 0.1)
        self.cursor_path_gen = iter(self.compute_next_cursor_position())
        self.cursor_position = None
        self.cursor_color_key = 'cursorcolor'
        self.gain_ratio = 0.8  # The proportion of the reticle area the cursor should cover
        self.response_time = 0
        self.joystick = None
        self.silent = silent

        # Tracking off-target penalty state
        self._offcenter_interval_timer = 0  # ms accumulated since last -3 penalty
        # Tracking on-target gain state
        self._ontarget_interval_timer = 0   # ms accumulated since last +1 gain
        self._flash_timer = 0
        self._flash_visible = False
        self._flash_widget = None

        if not REPLAY_MODE:
            joysticks = get_joysticks()
            if len(joysticks) > 0:
                self.joystick = joysticks[0]
                self.joystick.open()
            else:
                self.joystick = None
                if self.silent == False:
                    pass
                    # errors.add_error(_('No joystick found'))

        if self.joystick is not None:
            pass
            # self.joystick.push_handlers(self.win)

    def get_response_timers(self):
        return [self.response_time]


    def create_widgets(self):
        super().create_widgets()

        # Ensure task_container is valid
        if not hasattr(self, 'task_container') or self.task_container is None:
            self.task_container = self.container

        # Compute a square reticle that always fits inside the target container.
        # When using narrow placements (e.g., `topright`) the container width can be
        # significantly smaller than its height, which previously caused the reticle
        # to overflow and appear cropped. By clamping the size to the smallest
        # dimension we guarantee the widget always remains fully visible.
        max_size = min(self.task_container.w, self.task_container.h)
        if max_size <= 0:
            # Fallback: use container dimensions directly
            max_size = min(self.container.w, self.container.h) if self.container else self.win.width * 0.1

        side = max_size
        l = self.task_container.l + (self.task_container.w - side) / 2
        b = self.task_container.b + (self.task_container.h - side) / 2
        w = h = side

        # Ensure valid dimensions
        if w <= 0 or h <= 0:
            w = h = max(50, self.win.width * 0.1)
            l = self.task_container.l + (self.task_container.w - w) / 2
            b = self.task_container.b + (self.task_container.h - h) / 2

        self.add_widget('reticle', Reticle, container=Container('reticle', l, b, w, h),
                       target_proportion=self.parameters['targetproportion'],
                       cursorcolor=self.parameters['cursorcolor'])
        self.reticle = self.widgets['track_reticle']

        # Compute cursor movement constraints as soon as the reticle is created
        self.reticle_container = self.reticle.container
        self.xgain = (self.reticle_container.w * self.gain_ratio)/2
        self.ygain = (self.reticle_container.h * self.gain_ratio)/2
        self.cursor_position = next(self.cursor_path_gen)

        # Red flash overlay covering the entire tracking area (off-target penalty feedback)
        from core.widgets import Frame
        self._flash_widget = self.add_widget('track_flash', Frame,
                                             container=Container('track_flash',
                                                                  self.task_container.l,
                                                                  self.task_container.b,
                                                                  self.task_container.w,
                                                                  self.task_container.h),
                                             border_thickness=0.06,
                                             border_color=C['RED'],
                                             fill_color=None,
                                             draw_order=self.m_draw + 20)


    def compute_next_plugin_state(self):
        if super().compute_next_plugin_state() == 0:
            return

        # In case of replay, do not compute cursor position.
        # : the ReplayScheduler will master it.
        if not REPLAY_MODE: 
            self.cursor_position = next(self.cursor_path_gen)

        self.cursor_color_key = 'cursorcolor' if self.reticle.is_cursor_in_target() \
                    else 'cursorcoloroutside'
        self.log_performance('cursor_in_target', self.reticle.is_cursor_in_target())
        self.log_performance('center_deviation', self.reticle.return_deviation())

        if not self.reticle.is_cursor_in_target():  # A response is needed
            self.response_time += self.parameters['taskupdatetime']

            self._ontarget_interval_timer = 0  # Reset gain timer when off target

            # Off-target penalty: -3 health every 500ms, with red flash (no sound)
            self._offcenter_interval_timer += self.parameters['taskupdatetime']
            if self._offcenter_interval_timer >= 500:
                self._offcenter_interval_timer = 0
                from plugins.healthbar_bus import post_event
                post_event('TRACK_OFFCENTER', source='track')
                self._trigger_flash()
        else:
            if self.response_time > 0:  # The cursor drift has been recovered
                self.log_performance('response_time', self.response_time)
                self.response_time = 0
            self._offcenter_interval_timer = 0  # Reset interval when back on target

            # On-target gain: +1 health every 500ms
            self._ontarget_interval_timer += self.parameters['taskupdatetime']
            if self._ontarget_interval_timer >= 750:
                self._ontarget_interval_timer = 0
                from plugins.healthbar_bus import post_event
                post_event('TRACK_ONTARGET', source='track')

        # Decrement flash timer
        if self._flash_timer > 0:
            self._flash_timer -= self.parameters['taskupdatetime']
            if self._flash_timer <= 0:
                self._flash_visible = False


    def _trigger_flash(self, duration_ms=250):
        """Trigger a brief red border flash on the tracking area."""
        self._flash_timer = duration_ms
        self._flash_visible = True

    def refresh_widgets(self):
        if super().refresh_widgets() == 0:
            return
        self.reticle.set_cursor_position(*self.cursor_position)
        self.reticle.set_cursor_color(self.parameters[self.cursor_color_key])
        self.reticle.set_target_proportion(self.parameters['targetproportion'])

        # Show/hide the red flash overlay
        if self._flash_widget is not None:
            self._flash_widget.set_visibility(self._flash_visible)


    def compute_next_cursor_position(self):
        # Adapted from Comstock et al., (1992) : the first MATB documentation
        xsin, ysin = 0, 0
        xincr, yincr = 0.005, 0.006  # Cursor (x, y) asynchroneous speeds

        cursorx, cursory = 0, 0
        moffx, moffy = 0, 0

        while True:
            # Must wait the drawing of the reticle to evaluate x & y gain
            if f'{self.alias}_reticle' in self.widgets.keys():
                xsin = xsin + xincr if xsin < 2*pi else 0
                ysin = ysin + yincr if ysin < 2*pi else 0

                cursorx = sin(xsin) * self.xgain
                cursory = sin(ysin) * self.ygain

                compx, compy = 0, 0
                # Potential compensations of cursor movement
                # If the automode is enabled, apply automatic compensation to the cursor drift
                if self.parameters['automaticsolver'] == True:
                    compx = 1 if -self.reticle.cursor_relative[0] >= 0 else -1
                    compy = 1 if -self.reticle.cursor_relative[1] >= 0 else -1

                # Else if a manual input (joystick) is recorded, apply its offset to the cursor,
                # as a function of its gain
                elif self.joystick is not None:
                    if self.parameters['inverseaxis'] == False:
                        compx, compy = self.joystick.x, -self.joystick.y
                    else:
                        compx, compy = -self.joystick.x, self.joystick.y
                    logger.record_input(self.alias, 'joystick_x', compx)
                    logger.record_input(self.alias, 'joystick_y', compy)

                compx = compx * self.parameters['joystickforce']
                compy = compy * self.parameters['joystickforce']

                moffx = moffx + compx
                moffy = moffy + compy

                cursorx = cursorx + moffx
                cursory = cursory + moffy

                limitx = min(max(cursorx, -self.reticle.container.w/2), self.reticle.container.w/2)
                limity = min(max(cursory, -self.reticle.container.h/2), self.reticle.container.h/2)

                # If outside reticle limits, compensate cursor position
                # Neutralize the joystick only if it does not go toward the center
                if limitx != cursorx:
                    diff = cursorx-limitx
                    cursorx -= diff
                    if compx !=0 and diff/compx > 0:  # Same sign
                        moffx -= (diff + compx * self.parameters['joystickforce'])

                if limity != cursory:
                    diff = cursory-limity
                    cursory -= diff
                    if compy !=0 and diff/compy > 0:  # Same sign
                        moffy -= (diff + compy * self.parameters['joystickforce'])
                yield (cursorx, cursory)
            else:
                yield (0, 0)

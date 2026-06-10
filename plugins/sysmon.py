# Copyright 2023, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

import threading
import struct
import math
import io
import wave
from pathlib import Path

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

def _make_wav_bytes(frequency, duration_ms, volume=0.7, sample_rate=44100):
    """Generate a sine wave tone as WAV bytes in memory."""
    n_samples = int(sample_rate * duration_ms / 1000)
    fade = int(0.005 * sample_rate)  # 5ms fade in/out to avoid clicks
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        for i in range(n_samples):
            t = i / sample_rate
            f = 1.0
            if i < fade:
                f = i / fade
            elif i > n_samples - fade:
                f = (n_samples - i) / fade
            v = int(32767 * volume * f * math.sin(2 * math.pi * frequency * t))
            w.writeframes(struct.pack('<h', v))
    return buf.getvalue()

def play_beep(frequency=300, duration=100, repeat=1, gap=60):
    """Play a beep tone through the sound card using winsound.PlaySound.
    
    Args:
        frequency: Tone frequency in Hz
        duration: Duration of each beep in ms
        repeat: Number of times to repeat
        gap: Gap between repeats in ms
    """
    if HAS_WINSOUND:
        def _beep():
            try:
                import time
                wav_bytes = _make_wav_bytes(frequency, duration)
                for i in range(repeat):
                    winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
                    if i < repeat - 1:
                        time.sleep(gap / 1000.0)
            except Exception:
                pass
        threading.Thread(target=_beep, daemon=True).start()

def init_audio():
    """No-op — PlaySound doesn't need pre-initialization."""
    pass

from core.pseudorandom import choice, sample
from core.container import Container
from core.constants import COLORS as C, FONT_SIZES as F, Group as G
from core.widgets import Scale, Light, Simpletext, TimeoutBar, AutomodeIndicator
from core.widgets.abstractwidget import AbstractWidget
from plugins.abstract import AbstractPlugin
from pyglet.text import Label
from pyglet.gl import GL_QUADS, GL_LINES
from pyglet.media import Player, load


class BoxedText(AbstractWidget):
    """A text widget with a colored background and border for better visibility"""
    def __init__(self, name, container, win, text, font_size=F['SMALL'], 
                 text_color=C['BLACK'], background_color=C['BACKGROUND'], 
                 border_color=C['BLACK'], draw_order=1):
        super().__init__(name, container, win)

        # Create background rectangle
        self.border_vertices = self.vertice_border(self.container)
        
        # Background
        self.add_vertex('background', 4, GL_QUADS, G(self.m_draw + draw_order), 
                       ('v2f/static', self.border_vertices),
                       ('c4B/static', background_color*4))

        # Border
        self.add_vertex('border', 8, GL_LINES, G(self.m_draw + draw_order + 1),
                       ('v2f/static', self.vertice_strip(self.border_vertices)),
                       ('c4B/static', border_color*8))

        # Text (multiline, will shrink to fit)
        x = self.container.cx
        y = self.container.cy
        self._font_size = font_size
        self._min_font_size = 8
        # Use multiline Label with width equal to container width (in pixels)
        self.vertex['text'] = Label(text,
                       font_size=self._font_size,
                       x=x, y=y,
                       anchor_x='center', anchor_y='center',
                       color=text_color, group=G(self.m_draw + draw_order + 2),
                       font_name=self.font_name,
                       width=int(self.container.w),
                       multiline=True)

    def set_text(self, text):
        if text == self.get_text():
            return
        lbl = self.vertex['text']
        lbl.text = text
        # Shrink font until text height fits inside container (with small padding)
        max_h = int(self.container.h * 0.9)
        # If current content_height is not available, try to access layout height
        try:
            content_h = lbl.content_height
        except Exception:
            content_h = getattr(lbl, 'content_height', None) or 0

        while getattr(lbl, 'content_height', 0) > max_h and lbl.font_size > self._min_font_size:
            lbl.font_size = max(self._min_font_size, int(lbl.font_size * 0.9))
        self.logger.record_state(self.name, 'text', text)

    def get_text(self):
        return self.vertex['text'].text

    def set_colors(self, text_color=None, background_color=None, border_color=None):
        if text_color is not None:
            self.vertex['text'].color = text_color
        if background_color is not None:
            self.on_batch['background'].colors[:] = background_color*4
        if border_color is not None:
            self.on_batch['border'].colors[:] = border_color*8


class Sysmon(AbstractPlugin):
    def __init__(self, taskplacement='topleft', taskupdatetime=200):
        super().__init__(taskplacement, taskupdatetime)

        self.keys = {'Q', 'W', 'E', 'R', 'T', 'Y'}
        self.moving_seed = 1                # Useful for pseudorandom generation of 
                                            # multiple values at once (arrows move)

        new_par = dict(alerttimeout=7000, automaticsolver=False, automaticsolverdelay=2000,
                       displayautomationstate=True, automationlabel='', allowanykey=False, feedbackduration=1500,
                       showtimeoutbar=False,

                       feedbacks=dict(positive=dict(active=True, color=C['GREEN']),
                                      negative=dict(active=True, color=C['RED'])),

                       lights=dict([('1', dict(name='T', failure=False, default='on',
                                     oncolor=C['GREEN'], key='T', on=True)),
                                    ('2', dict(name='Y', failure=False, default='off',
                                     oncolor=C['RED'], key='Y', on=False))]),

                       scales=dict([('1', dict(name='Q', failure=False, side=0, key='Q')),
                                    ('2', dict(name='W', failure=False, side=0, key='W')),
                                    ('3', dict(name='E', failure=False, side=0, key='E')),
                                    ('4', dict(name='R', failure=False, side=0, key='R'))]),

                       # Report feature parameters
                       report=dict(active=False, text='REPORT', 
                                  text_color=C['WHITE'], 
                                  background_color=(139, 0, 0, 255),  # Dark red background
                                  border_color=C['BLACK'],
                                  duration=7000, font_size=F['LARGE'])
                       )

        self.parameters.update(new_par)

        # Add private parameters
        # to any gauge
        for gauge in self.get_all_gauges():
            gauge.update({'_failuretimer':None, '_onfailure':False, '_milliresponsetime':0,
                          '_freezetimer':None, '_penalty_stage':0})  # Track penalty stages (0, 1, 2, 3, 4)

        # and to scale only
        for gauge in self.get_scale_gauges():
            gauge.update({'_pos':5, '_zone':0, '_feedbacktimer':None, '_feedbacktype':None})

        # Add private parameters for report feature
        self.parameters['report'].update({'_timer':None, '_visible':False})

        self.automode_position = (0.5, 0.05)
        self.scale_zones = {1: list(range(3)), 0: list(range(3, 8)), -1: list(range(8, 11))}
        self._last_automode_indicator_state = False
        self._automation_start_sound = None
        self._automation_start_sound_player = None


    def get_response_timers(self):
        return [g['_milliresponsetime'] for g in self.get_all_gauges()]


    def create_widgets(self):
        super().create_widgets()
        
        # Initialize audio system early to avoid delay on first beep
        init_audio()
        try:
            sound_path = Path(__file__).resolve().parents[1] / "includes" / "sounds" / "third_party" / "starting_automation.mp3"
            self._automation_start_sound = load(str(sound_path), streaming=False)
        except Exception:
            self._automation_start_sound = None
        
        # Widgets coordinates (the left l coordinate is variable)
        scale_w = self.task_container.w * 0.1
        scale_b = self.task_container.b + self.task_container.h * 0.15
        scale_h = self.task_container.h * 0.5

        light_w = self.task_container.w * 0.4
        light_b = self.task_container.b + self.task_container.h * 0.75
        light_h = self.task_container.h * 0.15

        from core.widgets import Frame
        
        for scale_n, scale in self.parameters['scales'].items():
            scale_l = self.task_container.l + (self.task_container.w / 4) * (int(scale_n) - 1) + \
                      self.task_container.w/8 - scale_w/2
            scale_container = Container(f'scale_{scale_n}', scale_l, scale_b, scale_w, scale_h)

            scale['widget'] = self.add_widget(f"scale{str(scale_n)}", Scale,
                                             container=scale_container,
                                             label=scale['name'],
                                             arrow_position=scale['_pos'])
            
            # Create individual red flash overlay for this scale
            flash_container = Container(f'scale_flash_{scale_n}', 
                                        scale_l - scale_w * 0.1, 
                                        scale_b - scale_h * 0.05,
                                        scale_w * 1.2, 
                                        scale_h * 1.1)
            scale['_flash_widget'] = self.add_widget(f'scale_flash_{scale_n}', Frame,
                                                     container=flash_container,
                                                     border_thickness=0.08,
                                                     border_color=C['RED'],
                                                     fill_color=None,
                                                     draw_order=self.m_draw+20)
            scale['_flash_visible'] = False
            scale['_flash_timer'] = 0

        for light_n, light in self.parameters['lights'].items():
            light_l = self.task_container.l + (self.task_container.w/2) * (int(light_n)-1) + \
                      self.task_container.w/4 - light_w/2
            light_container = Container(f'light_{light_n}', light_l, light_b, light_w, light_h)

            light['widget'] = self.add_widget(f'light{str(light_n)}', Light,
                                             container=light_container,
                                             label=light['name'],
                                             color=self.determine_light_color(light))
            
            # Create individual red flash overlay for this light (T and Y buttons)
            flash_container = Container(f'light_flash_{light_n}',
                                        light_l - light_w * 0.02,
                                        light_b - light_h * 0.1,
                                        light_w * 1.04,
                                        light_h * 1.2)
            light['_flash_widget'] = self.add_widget(f'light_flash_{light_n}', Frame,
                                                     container=flash_container,
                                                     border_thickness=0.06,
                                                     border_color=C['RED'],
                                                     fill_color=None,
                                                     draw_order=self.m_draw+20)
            light['_flash_visible'] = False
            light['_flash_timer'] = 0

        # Create report widget (initially hidden)
        report_container = Container('report', self.task_container.l, 
                                   self.task_container.b + self.task_container.h * 0.9,
                                   self.task_container.w, self.task_container.h * 0.1)
        self.add_widget('report', BoxedText,
                       container=report_container,
                       text=self.parameters['report']['text'],
                       font_size=self.parameters['report']['font_size'],
                       text_color=self.parameters['report']['text_color'],
                       background_color=self.parameters['report']['background_color'],
                       border_color=self.parameters['report']['border_color'])

        # Timeout bar (toggle with showtimeoutbar parameter in scenario/config).
        if self.parameters['showtimeoutbar']:
            bar_h = max(8, int(self.task_container.h * 0.025))
            bar_container = Container('sysmon_timeout_bar',
                                      self.task_container.l,
                                      self.task_container.b,
                                      self.task_container.w,
                                      bar_h)
            self.add_widget('timeout_bar', TimeoutBar, container=bar_container, draw_order=25)

        # Automation indicator: small square + label, anchored right of screen centre.
        # Shifted right of centre so it clears any bottom-left widgets.
        sq = 36
        label_w = 160
        label_h = 22
        offset_right = 80   # px right of screen centre
        group_l = self.win.width // 2 + offset_right
        group_b = self.win.height // 2 + 80
        ind_container = Container('sysmon_automode_ind',
                                  group_l,
                                  group_b,
                                  sq, sq)
        self.add_widget('automode_indicator', AutomodeIndicator,
                        container=ind_container, draw_order=60)
        label_container = Container('sysmon_automode_lbl',
                                    group_l - (label_w - sq) // 2,
                                    group_b - label_h - 8,
                                    label_w, label_h)
        self.add_widget('automode_label', Simpletext,
                        container=label_container,
                        text='Automation Status',
                        x=0.5, y=0.5,
                        font_size=F['SMALL'],
                        draw_order=60)



    def compute_next_plugin_state(self):
        if super().compute_next_plugin_state() == 0:
            return

        # Handle flash timers for all gauges (scales and lights)
        for gauge in list(self.parameters['scales'].values()) + list(self.parameters['lights'].values()):
            if gauge.get('_flash_timer', 0) > 0:
                gauge['_flash_timer'] -= self.parameters['taskupdatetime']
                if gauge['_flash_timer'] <= 0:
                    gauge['_flash_visible'] = False
        
        # For the gauges that are on failure
        for gauge in self.get_gauges_on_failure():
            # Decrement their failure timer / increment their response time
            gauge['_failuretimer'] -= self.parameters['taskupdatetime']
            gauge['_milliresponsetime'] += self.parameters['taskupdatetime']
            
            # Progressive penalty system (only when automation is OFF)
            # At 2s, 3s, 4s, 5s: health penalty only, no beep/flash until final MISS
            if not self.parameters['automaticsolver']:
                response_sec = gauge['_milliresponsetime'] / 1000.0
                
                # Check each penalty stage threshold - health penalty only
                if response_sec >= 2.0 and gauge['_penalty_stage'] < 1:
                    gauge['_penalty_stage'] = 1
                    from plugins.healthbar_bus import post_event
                    post_event('SYSMON_DELAY_1', source='sysmon')
                    
                elif response_sec >= 3.0 and gauge['_penalty_stage'] < 2:
                    gauge['_penalty_stage'] = 2
                    from plugins.healthbar_bus import post_event
                    post_event('SYSMON_DELAY_2', source='sysmon')
                    
                elif response_sec >= 4.0 and gauge['_penalty_stage'] < 3:
                    gauge['_penalty_stage'] = 3
                    from plugins.healthbar_bus import post_event
                    post_event('SYSMON_DELAY_3', source='sysmon')
                    
                elif response_sec >= 5.0 and gauge['_penalty_stage'] < 4:
                    gauge['_penalty_stage'] = 4
                    from plugins.healthbar_bus import post_event
                    post_event('SYSMON_DELAY_4', source='sysmon')

            # If the failure timer has ended by itself, stop failure and trigger a negative feedback
            # if possible (scale gauges)
            if gauge['_failuretimer'] <= 0:
                self.stop_failure(gauge, success=False)

        for gauge in self.get_scale_gauges():
            if gauge['_feedbacktimer'] is not None:
                gauge['_feedbacktimer'] -= self.parameters['taskupdatetime']
                if gauge['_feedbacktimer'] <= 0:
                    gauge['_feedbacktimer'] = None
                    gauge['_feedbacktype'] = None

        # Handle report timer
        if self.parameters['report']['_timer'] is not None:
            self.parameters['report']['_timer'] -= self.parameters['taskupdatetime']
            if self.parameters['report']['_timer'] <= 0:
                self.parameters['report']['_timer'] = None
                self.parameters['report']['_visible'] = False


        # Compute arrows next position
        for scale_n, scale in self.parameters['scales'].items():
            self.moving_seed += 1
            # Manage the case where the arrow must change its zone
            if scale['_pos'] not in self.scale_zones[scale['_zone']]:
                scale['_pos'] = sample(self.scale_zones[scale['_zone']], self.alias, 
                                       self.scenario_time, self.moving_seed)
            else:   # Move into a delimited zone
                direction = sample([-1, 1], self.alias, self.scenario_time, self.moving_seed)
                if scale['_pos'] + direction in self.scale_zones[scale['_zone']]:
                    scale['_pos'] += direction
                else:
                    scale['_pos'] -= direction

            # If the gauge freeze timer is not null, freeze its arrow (pos = )
            if scale['_freezetimer'] is not None and isinstance(scale['_freezetimer'], int):
                scale['_freezetimer'] -= self.parameters['taskupdatetime']
                if scale['_freezetimer'] > 0:
                    # Here, freeze position
                    scale['_pos'] = 5  # TODO: Check central scale value
                else:
                    scale['_freezetimer'] = None


        # Check for failure
        for gauge in self.get_gauges_key_value('failure', True):
            self.start_failure(gauge)


    def refresh_widgets(self):
        if super().refresh_widgets() == 0:
            return
        
        # Handle individual red flash effects for each scale
        for scale_n, scale in self.parameters['scales'].items():
            flash_widget = scale.get('_flash_widget')
            if flash_widget is not None:
                flash_widget.set_visibility(scale.get('_flash_visible', False))
        
        # Handle individual red flash effects for each light (T and Y buttons)
        for light_n, light in self.parameters['lights'].items():
            flash_widget = light.get('_flash_widget')
            if flash_widget is not None:
                flash_widget.set_visibility(light.get('_flash_visible', False))
        
        for scale_n, scale in self.parameters['scales'].items():
            scale['widget'].set_arrow_position(scale['_pos'])

            if scale['_onfailure']:
            # Keep the whole gauge visibly red until the failure is cleared
                scale['widget'].set_feedback_color(C['RED'])
                scale['widget'].set_feedback_visibility(True)
            
            if scale['_feedbacktimer'] is not None:
                color = self.parameters['feedbacks'][scale['_feedbacktype']]['color']
                scale['widget'].set_feedback_color(color)
                scale['widget'].set_feedback_visibility(True)

            # Feedback timer is over and the feedback is yet visible
            # Hide the feedback
            else:
                scale['widget'].set_feedback_visibility(False)

        for light_n, light in self.parameters['lights'].items():
            light['widget'].set_color(self.determine_light_color(light))

        for gauge in self.get_all_gauges():
            gauge['widget'].set_label(gauge['name'])

        # Defensive: ensure report parameter structure is a dict (avoid accidental overwrite)
        if not isinstance(self.parameters.get('report'), dict):
            self.parameters['report'] = dict(active=False, text='REPORT',
                                             text_color=C['WHITE'],
                                             background_color=(139, 0, 0, 255),
                                             border_color=C['BLACK'],
                                             duration=7000, font_size=F['LARGE'],
                                             _timer=None, _visible=False)

        # Handle report widget visibility
        if self.parameters['report']['_visible']:
            self.get_widget('report').show()
        else:
            self.get_widget('report').hide()

        # Timeout bar: show while any gauge is in failure, depleting over alerttimeout.
        timeout_bar = self.get_widget('timeout_bar')
        if timeout_bar is not None:
            gauges_on_failure = self.get_gauges_on_failure()
            if len(gauges_on_failure) > 0:
                alert_ms = float(self.parameters['alerttimeout'])
                # Show the most-urgent gauge (smallest fraction remaining)
                fracs = [max(0.0, 1.0 - g['_milliresponsetime'] / alert_ms)
                         for g in gauges_on_failure]
                timeout_bar.set_fraction(min(fracs))
                if not timeout_bar.is_visible():
                    timeout_bar.show()
            else:
                if timeout_bar.is_visible():
                    timeout_bar.hide()

        # Automation indicator: green when the session label is 'AUTO' (stays green even
        # during the low-reliability window where automaticsolver may be False).
        automode_ind = self.get_widget('automode_indicator')
        if automode_ind is not None:
            is_auto_label = self.parameters.get('automationlabel', '') == 'AUTO'
            automode_ind.set_active(is_auto_label)
            if is_auto_label and not self._last_automode_indicator_state:
                self._play_automation_start_sound()
            self._last_automode_indicator_state = is_auto_label



    def determine_light_color(self, light):
        color = light['oncolor'] if light['on'] == True else C['BACKGROUND']
        return color

    def _play_automation_start_sound(self):
        if self._automation_start_sound is None:
            return
        try:
            self._automation_start_sound_player = Player()
            self._automation_start_sound_player.queue(self._automation_start_sound)
            self._automation_start_sound_player.play()
        except Exception:
            pass

    def _trigger_flash(self, gauge=None, duration_ms=300):
        """Trigger a red flash effect on a specific gauge's widget.
        
        Args:
            gauge: The gauge dict to flash. If None, flashes all gauges on failure.
            duration_ms: Duration of the flash in milliseconds.
        """
        if gauge is not None:
            # Flash specific gauge
            gauge['_flash_timer'] = duration_ms
            gauge['_flash_visible'] = True
        else:
            # Flash all gauges currently on failure
            for g in self.get_gauges_on_failure():
                g['_flash_timer'] = duration_ms
                g['_flash_visible'] = True


    def start_failure(self, gauge):
        if gauge['_onfailure'] == True:
            pass  # TODO : warn in case of multiple failure on the same gauge
        else:
            gauge['_onfailure'] = True
            if 'default' in gauge.keys():  # Light case
                gauge['on'] = not gauge['default'] == 'on'
            else:  # Scale case
                if gauge['side'] not in [-1, 1]:
                    add = self.get_gauge_key(gauge) # Specify a gauge integer to generate
                                                    # a unique seed    
                    gauge['side'] = choice([-1, 1], self.alias, self.scenario_time, int(add))
                gauge['_zone'] = gauge['side']
            
        
        gauge['failure'] = False

        # Schedule failure timing
        delay = self.parameters['automaticsolverdelay'] if self.parameters['automaticsolver'] \
            else self.parameters['alerttimeout']
        gauge['_failuretimer'] = delay


    def stop_failure(self, gauge, success=False):
        # Reset the gauge failure timer
        gauge['_onfailure'] = False
        gauge['_failuretimer'] = None

        # Set the (potential) feedback type (ft)
        ft = 'positive' if self.parameters['automaticsolver'] or success == True else 'negative'

        # Does this feedback type (positive or negative) is currently active ?
        # If so, set the feedback type and duration, if the gauge has got one
        # (the feedback widget is refreshed by the refresh_widget method)
        if self.parameters['feedbacks'][ft]['active'] and '_feedbacktimer' in gauge:
            self.set_scale_feedback(gauge, ft)

        # Feed the freeze timer with feedback duration (1.5 by default) if the response is good
        if success:
            gauge['_freezetimer'] = self.parameters['feedbackduration']

        # IDEA: do we need to distinguish manual detection (hit) from automatic detection ?
        # Evaluate performance in terms of signal detection and response time
        if ft == 'positive':
            sdt_string, rt = 'HIT', gauge['_milliresponsetime']
        else:
            sdt_string, rt = 'MISS', float('nan')
            # Play error beep and flash when participant failed to respond in time (MISS)
            play_beep(frequency=180, duration=150, repeat=2, gap=100)  # Lower tone for MISS
            self._trigger_flash(gauge)
        sdt_string = 'HIT' if ft == 'positive' else 'MISS'


        from plugins.healthbar_bus import post_event
        post_event('HIT' if sdt_string == 'HIT' else 'MISS', source='sysmon')

        self.log_performance('name', gauge['name'])
        self.log_performance('signal_detection', sdt_string)
        self.log_performance('response_time', rt)

        # Reset gauge to its nominal (default) state
        if 'default' in gauge.keys():  # Light case
            gauge['on'] = gauge['default'] == 'on'
        else:  # Scale case
            gauge['_zone'] = 0
        gauge['_milliresponsetime'] = 0
        gauge['_penalty_stage'] = 0  # Reset penalty stage


    def get_gauges_key_value(self, key, value):
        gauge_list = list()
        for gauge in self.get_all_gauges():
            if gauge[key] == value:
                gauge_list.append(gauge)
        return gauge_list


    def get_gauge_by_key(self, key):
        return self.get_gauges_key_value('key', key)[0]


    def get_gauge_key(self, gauge):
        for key in ['lights', 'scales']:
            for k, v in self.parameters[key].items():
                if gauge == v:
                    return k


    def get_gauges_on_failure(self):
        return self.get_gauges_key_value('_onfailure', True)


    def get_scale_gauges(self):
        return [g for _,g in self.parameters['scales'].items()]


    def get_light_gauges(self):
        return [g for _,g in self.parameters['lights'].items()]


    def get_all_gauges(self):
        return [g for g in self.get_scale_gauges() + self.get_light_gauges()]


    def set_scale_feedback(self, gauge, feedback_type):
        # Set the feedback type and duration, if the gauge has got one
        # (the feedback widget is refreshed by the refresh_widget method)
        gauge['_feedbacktype'] = feedback_type
        gauge['_feedbacktimer'] = self.parameters['feedbackduration']


    def do_on_key(self, key, state, emulate):
        key = super().do_on_key(key, state, emulate)
        if key is None:
            return

        if state == 'press':
            gauge = self.get_gauge_by_key(key)
            if key in [g['key'] for g in self.get_gauges_on_failure()]:
                self.stop_failure(gauge=gauge, success=True)
            else:
                self.log_performance('name', gauge['name'])
                self.log_performance('signal_detection', 'FA')
                self.log_performance('response_time', float('nan'))

                # in Sysmon.do_on_key, when logging FA:
                from plugins.healthbar_bus import post_event
                post_event('FA', source='sysmon')
                
                # Play error beep and flash for False Alarm
                play_beep(frequency=220, duration=100, repeat=2, gap=80)
                self._trigger_flash(gauge)

                # Set a negative feedback if relevant
                if self.parameters['feedbacks']['negative']['active']:
                    self.set_scale_feedback(gauge, 'negative')

    def report(self, text=None):
        """
        Public method that can be triggered from the scenario file: "...;sysmon;report"
        Optionally accepts a text argument: "...;sysmon;report;Some text"
        Shows a red textbox with the provided text (or default) for the specified duration
        """
        if text is not None:
            try:
                self.get_widget('report').set_text(text)
            except Exception:
                # Fallback: set parameter default text
                self.parameters['report']['text'] = text
        self.parameters['report']['_visible'] = True
        self.parameters['report']['_timer'] = self.parameters['report']['duration']

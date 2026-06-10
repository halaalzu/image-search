# plugins/healthbar.py
# Minimal, MATB-style plugin that draws a bar and updates with performance events

from plugins.abstract import AbstractPlugin
from plugins.healthbar_bus import drain_events
from core.container import Container
from core.constants import COLORS as C, FONT_SIZES as F
from core.widgets import HealthBar, Simpletext

class Healthbar(AbstractPlugin):
    """
    A small bar placed near the chrono/scheduler that tracks session "health".
    Health goes down on MISS/FA, up on HIT/CORRECT, and regenerates slowly.
    """
    def __init__(self, taskplacement='invisible', taskupdatetime=80):
        super().__init__(taskplacement, taskupdatetime)
        
        # Force health bars to render on the topmost layer (above all other widgets)
        self.m_draw = 999

        # Tunables (you can tweak live via scenario or parameters)
        self.parameters.update(dict(
            max_health=100.0,
            start_health=100.0,
            min_health=0.0,

            # SYSTEM MONITORING BAR 
            sysmon_gain_hit=10.0,
            sysmon_penalty_delay=3.0,
            sysmon_penalty_miss=9.0,
            sysmon_penalty_fa=10.0,
            sysmon_color_good=(100, 255, 150, 255),     # Bright green
            sysmon_color_bad=(255, 80, 80, 255),        # Bright red
            sysmon_label='SYSMON',

            #  NAVIGATION BAR (Tracking Task) 
            nav_gain_ontarget=1.0,
            nav_penalty_offcenter=2.0,
            nav_color_good=(100, 255, 150, 255),        # Bright green
            nav_color_bad=(255, 80, 80, 255),           # Bright red
            nav_label='NAV',

            #  COMMUNICATIONS BAR 
            comms_gain_correct=15.0,
            comms_penalty_delay=4.0,
            comms_penalty_fa=12.0,
            comms_penalty_miss=12.0,
            comms_color_good=(100, 255, 150, 255),      # Bright green
            comms_color_bad=(255, 80, 80, 255),         # Bright red
            comms_label='COMMS',

            # UI sizing/colors - three bars below black line
            bar_length_ratio=0.144,   # Each bar: 14.4% of screen width (18% reduced by 20%)
            bar_thickness_ratio=0.30,  # 30% of screen height (reduced from 36%)
            bar_anchor='bottomright', # Align to screen bottom-right
            bar_margin_ratio=0.005,   # Very minimal margin (0.5%)
            border_color=(255, 255, 255, 255),  # Bright white border
            back_color=(40, 40, 45, 255),      # Dark background
            text_color=(255, 255, 255, 255),   # White text
            label_font='LARGE',
            value_font='LARGE',
            spacing_ratio=0.01,       # Spacing between bars
            top_margin_ratio=0.0,     # Position below black line (no extra margin)
            title_spacing_ratio=0.03  # Space between title and bar
        ))

        # Initialize three separate health values for each task
        self._health_sysmon = self.parameters['start_health']
        self._health_nav = self.parameters['start_health']
        self._health_comms = self.parameters['start_health']

    # ---- helpers

    def _clamp(self, v):
        p = self.parameters
        return max(p['min_health'], min(p['max_health'], v))
 
    # ---- state handling

    def show(self):
        """Override show to ensure all three healthbar widgets are visible"""
        super().show()
        # Show all three health bars
        for bar_key in ['healthbar_sysmon', 'healthbar_nav', 'healthbar_comms']:
            widget = self.get_widget(bar_key)
            if widget is not None:
                widget.show()

    def hide(self):
        """Override hide - for invisible placement, we keep widgets visible for feedback"""
        if self.parameters['taskplacement'] == 'invisible':
            self.visible = False
            self.update_can_receive_key()
        else:
            super().hide()

    # ---- widgets

    def create_widgets(self):
        # Call parent create_widgets to set up containers
        super().create_widgets()

        # Ensure window is available
        if self.win is None:
            return

        # Get parameters
        length_ratio = self.parameters['bar_length_ratio']
        thickness_ratio = self.parameters['bar_thickness_ratio']
        spacing_ratio = self.parameters['spacing_ratio']
        margin_ratio = self.parameters['bar_margin_ratio']
        top_margin_ratio = self.parameters['top_margin_ratio']
        anchor = self.parameters['bar_anchor']

        # Calculate individual bar dimensions (horizontal bars - side by side)
        w = self.win.width * length_ratio
        h = self.win.height * thickness_ratio
        w = max(10, w)
        h = max(10, h)

        spacing = self.win.width * spacing_ratio

        margin_x = self.win.width * margin_ratio
        margin_y = self.win.height * margin_ratio

        # Top margin to keep bars below the black line
        top_margin = self.win.height * top_margin_ratio

        # Calculate total space needed for all 3 bars (arranged horizontally)
        total_width = 3 * w + 2 * spacing
        total_height = h

        # Calculate starting position based on anchor (bottom-center, below black line)
        if 'left' in anchor:
            start_x = margin_x
        elif 'right' in anchor:
            # Adjust further to the right to avoid covering
            start_x = self.win.width - total_width - margin_x - (self.win.width * 0.02)
        elif 'center' in anchor:
            # Center horizontally
            start_x = (self.win.width - total_width) / 2
        else:
            start_x = (self.win.width - total_width) / 2

        if 'bottom' in anchor:
            # Position in the bottom area, below the black middle divider
            start_y = margin_y + (self.win.height * 0.05)
        elif 'top' in anchor:
            # Push bars down from top
            start_y = self.win.height - total_height - margin_y - top_margin
        else:  # center
            start_y = (self.win.height - total_height) / 2

        # Define three bars with different colors and labels and titles
        bars_config = [
            {
                'key': 'healthbar_sysmon',
                'label': self.parameters['sysmon_label'],
                'title': 'SYSTEM MONITORING',
                'good_color': self.parameters['sysmon_color_good'],
                'bad_color': self.parameters['sysmon_color_bad'],
                'index': 0
            },
            {
                'key': 'healthbar_nav',
                'label': self.parameters['nav_label'],
                'title': 'TRACKING',
                'good_color': self.parameters['nav_color_good'],
                'bad_color': self.parameters['nav_color_bad'],
                'index': 1
            },
            {
                'key': 'healthbar_comms',
                'label': self.parameters['comms_label'],
                'title': 'COMMUNICATIONS',
                'good_color': self.parameters['comms_color_good'],
                'bad_color': self.parameters['comms_color_bad'],
                'index': 2
            }
        ]

        # Create three different-colored bars side-by-side
        title_spacing = self.win.height * self.parameters['title_spacing_ratio']
        
        for config in bars_config:
            x = start_x + config['index'] * (w + spacing)
            y = start_y

            # Create black title label above the bar with very high draw order
            title_y = y + h + title_spacing
            title_container = Container(f"title_{config['key']}", x, title_y, w, 0)
            
            self.add_widget(f"title_{config['key']}", Simpletext,
                            container=title_container,
                            text=config['title'],
                            font_size=int(F['MEDIUM'] * 0.9),
                            color=C['BLACK'],
                            draw_order=1000)
            
            title_widget = self.get_widget(f"title_{config['key']}")
            if title_widget is not None:
                title_widget.show()

            bar_container = Container(f"container_{config['key']}", x, y, w, h)

            # Create the healthbar widget with high z-order rendering
            self.add_widget(config['key'], HealthBar,
                            container=bar_container,
                            max_health=self.parameters['max_health'],
                            min_health=self.parameters['min_health'],
                            good_color=config['good_color'],
                            bad_color=config['bad_color'],
                            back_color=self.parameters['back_color'],
                            border_color=self.parameters['border_color'],
                            text_color=self.parameters['text_color'],
                            label=config['label'],
                            orientation='vertical',
                            label_font_key=self.parameters['label_font'],
                            value_font_key=self.parameters['value_font'])
            
            # Force the widget to have high rendering order (on top of all other widgets)
            widget = self.get_widget(config['key'])
            if widget is not None:
                widget.m_draw = 999
                # Update vertex groups to reflect the new m_draw value
                if hasattr(widget, 'update_render_order'):
                    widget.update_render_order()

        # Initialize all three bars with their respective health values
        sysmon_widget = self.get_widget('healthbar_sysmon')
        if sysmon_widget is not None:
            sysmon_widget.set_health(self._health_sysmon)
            sysmon_widget.show()

        nav_widget = self.get_widget('healthbar_nav')
        if nav_widget is not None:
            nav_widget.set_health(self._health_nav)
            nav_widget.show()

        comms_widget = self.get_widget('healthbar_comms')
        if comms_widget is not None:
            comms_widget.set_health(self._health_comms)
            comms_widget.show()

    # ---- logic

    def compute_next_plugin_state(self):
        if super().compute_next_plugin_state() == 0:
            return

        # Consume performance events and route to correct health bar
        for _, kind, source, value in drain_events():
            k = (kind or '').upper()
        
            # SYSTEM MONITORING EVENTS
            if k == 'HIT':
                # Sysmon correct response: +10
                self._health_sysmon = self._clamp(self._health_sysmon + self.parameters['sysmon_gain_hit'])
            
            elif k in ('SYSMON_DELAY_1', 'SYSMON_DELAY_2', 'SYSMON_DELAY_3', 'SYSMON_DELAY_4'):
                # Sysmon delay penalty: -3
                self._health_sysmon = self._clamp(self._health_sysmon - self.parameters['sysmon_penalty_delay'])
            
            elif k == 'MISS':
                # Sysmon final timeout: -9
                self._health_sysmon = self._clamp(self._health_sysmon - self.parameters['sysmon_penalty_miss'])
            
            elif k == 'FA':
                # Sysmon false alarm: -10
                self._health_sysmon = self._clamp(self._health_sysmon - self.parameters['sysmon_penalty_fa'])
            
            # NAVIGATION/TRACKING EVENTS
            elif k == 'TRACK_ONTARGET':
                # Tracking cursor on-target: +1 every 500ms
                self._health_nav = self._clamp(self._health_nav + self.parameters['nav_gain_ontarget'])
            
            elif k == 'TRACK_OFFCENTER':
                # Tracking cursor off-target: -2 every 500ms
                self._health_nav = self._clamp(self._health_nav - self.parameters['nav_penalty_offcenter'])

            # COMMUNICATIONS EVENTS
            elif k == 'CORRECT':
                # Communications correct frequency: +15
                self._health_comms = self._clamp(self._health_comms + self.parameters['comms_gain_correct'])
            
            elif k in ('COMMS_DELAY_1', 'COMMS_DELAY_2', 'COMMS_DELAY_3', 'COMMS_DELAY_4'):
                # Communications delay penalty: -4
                self._health_comms = self._clamp(self._health_comms - self.parameters['comms_penalty_delay'])
            
            elif k in ('BAD_FREQ', 'BAD_RADIO', 'BAD_RADIO_FREQ', 'COMMS_FA'):
                # Communications wrong frequency/radio or false alarm: -12
                self._health_comms = self._clamp(self._health_comms - self.parameters['comms_penalty_fa'])
            
            elif k == 'COMMS_MISS':
                # Communications final timeout: -12
                self._health_comms = self._clamp(self._health_comms - self.parameters['comms_penalty_miss'])

    def refresh_widgets(self):
        # Update all three different health bars with their respective values
        sysmon_widget = self.get_widget('healthbar_sysmon')
        if sysmon_widget is not None:
            sysmon_widget.set_health(self._health_sysmon)
            # Keep it on top rendering layer
            if hasattr(sysmon_widget, 'm_draw'):
                sysmon_widget.m_draw = 9999

        nav_widget = self.get_widget('healthbar_nav')
        if nav_widget is not None:
            nav_widget.set_health(self._health_nav)
            # Keep it on top rendering layer
            if hasattr(nav_widget, 'm_draw'):
                nav_widget.m_draw = 9999

        comms_widget = self.get_widget('healthbar_comms')
        if comms_widget is not None:
            comms_widget.set_health(self._health_comms)
            # Keep it on top rendering layer
            if hasattr(comms_widget, 'm_draw'):
                comms_widget.m_draw = 9999
        
        # For invisible placement, ensure plugin is considered visible so parent refreshes
        was_visible = self.visible
        if self.parameters['taskplacement'] == 'invisible' and self.alive:
            self.visible = True
        
        # Call parent refresh_widgets
        result = super().refresh_widgets()
        
        # Restore visibility state for invisible placement
        if self.parameters['taskplacement'] == 'invisible':
            self.visible = was_visible if not self.alive else True
        
        return result if result != 0 else 1

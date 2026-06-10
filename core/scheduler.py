# Copyright 2023, by Julien Cegarra & Benoît Valéry. All rights reserved.
# Institut National Universitaire Champollion (Albi, France).
# License : CeCILL, version 2.1 (see the LICENSE file)

import sys
import os
import time
from pyglet.app import EventLoop
from time import perf_counter
from core.scenario import Event
from core.clock import Clock
from core.modaldialog import ModalDialog
from core.logger import logger
from core.utils import get_conf_value
from core.constants import REPLAY_MODE
from core.error import errors



class Scheduler:
    """
    This class manages events execution.
    """

    def __init__(self, window, scenario):

        self.win = window
        self.events = scenario.events
        self.plugins = scenario.plugins

        logger.log_manual_entry(f'Scheduler init: events={len(self.events)}, plugins={len(self.plugins)}', key='scheduler')

        # Attribute window to plugins in use, and push their handles to window
        for p in self.plugins:
            self.plugins[p].win = self.win
            if not REPLAY_MODE:
                self.win.push_handlers(self.plugins[p].on_key_press,
                                       self.plugins[p].on_key_release)

        logger.log_manual_entry(open('VERSION', 'r').read().strip(), key='version')

        if 'scheduling' in self.plugins:
            self.plugins['scheduling'].set_planning(self.events)

        # Link performance plugin to other plugins
        if 'performance' in self.plugins:
            self.plugins['performance'].plugins = self.plugins

        self.clock = Clock('main')
        self.pause_scenario_time = False
        self.scenario_time = 0

        # Live-reload support: remember scenario source path and mtime
        self.scenario_path = getattr(scenario, 'used_path', None)
        try:
            self._scenario_mtime = os.path.getmtime(self.scenario_path) if self.scenario_path else None
        except Exception:
            self._scenario_mtime = None
        self._last_mtime_check = 0.0

        # We store events in a list in case their execution is delayed by a blocking event
        self.events_queue = list()
        self.blocking_plugin = None

        # Store the plugins that could be paused by a *blocking* event
        self.paused_plugins = list()
        self.core_task_plugins = {'sysmon', 'track', 'communications', 'resman'}
        self.start_signal_sent = False
        self.end_signal_sent = False
        self.user_aborted = False
        
        # Track individually paused tasks (from pause events)
        self.task_pause_status = {}  # e.g., {'sysmon': True, 'track': False}

        # Create the event loop
        self.clock.schedule(self.update)
        self.event_loop = EventLoop()
        from time import perf_counter
        self._started_at = perf_counter()


    def initialize_plugins(self):
        pass


    def update(self, dt):    
        if self.win.modal_dialog is not None:
            return
        elif errors.is_empty() == False:
            errors.show_errors()
            
        self.update_timers(dt)
        self.update_active_plugins()
        self.execute_events()
        self.check_if_must_exit()


    def update_timers(self, dt):
        # Update timers with dt
        if not self.is_scenario_time_paused():
            self.scenario_time += dt
            logger.set_scenario_time(self.scenario_time)

        # Periodically check if scenario file changed on disk (once per second)
        try:
            now = time.time()
            if self.scenario_path and (now - self._last_mtime_check) > 1.0:
                self._last_mtime_check = now
                mtime = os.path.getmtime(self.scenario_path)
                if self._scenario_mtime is None:
                    self._scenario_mtime = mtime
                elif mtime != self._scenario_mtime:
                    logger.log_manual_entry(f'Scenario file changed on disk: reloading {self.scenario_path}', key='scenario_reload')
                    self._scenario_mtime = mtime
                    self.reload_events_from_file()
        except Exception:
            pass


    def update_active_plugins(self):
        # Check if there are active plugins...
        if len(self.get_active_plugins()) > 0:
            # ... if so, update them
            [p.update(self.scenario_time) for p in self.get_active_plugins()]


    def check_if_must_exit(self):
        # If the windows has been killed, exit the program
        if self.win.alive == False:
            self.user_aborted = True
            # Be careful to stop all the plugins in case they’re not
            # (so we have a stop time for each plugin, in case we must compute this somewhere)
            for p_name, plugin in self.plugins.items():
                if plugin.alive == True:
                    stop_event = Event(0, int(self.scenario_time), p_name, 'stop')
                    self.execute_one_event(stop_event)
            self.exit()
            return

        # If a modal was just closed, allow a small grace period for the
        # scheduler to process initial events before deciding to exit. This
        # avoids a race where closing a startup modal immediately triggers
        # an exit in the same update tick.
        try:
            last_closed = getattr(self.win, '_modal_closed_at', None)
            if last_closed is not None and (perf_counter() - last_closed) < 0.25:
                return
        except Exception:
            pass

        # Avoid exiting too quickly after startup — give plugins a short
        # chance to initialize. This prevents immediate exit if plugin
        # instantiation is delayed or modal was just dismissed.
        try:
            if (perf_counter() - self._started_at) < 0.5:
                return
        except Exception:
            pass

        # If no active plugin and no remaining queued event, close OpenMATB.
        if len(self.get_active_plugins()) == 0 and len(self.events_queue) == 0:
            self.exit()


    def execute_events(self):
        # Detect a potential blocking plugin
        active_blocking_plugin = self.get_active_blocking_plugin()

        # Execute scenario events in case the scenario timer is running
        if not self.is_scenario_time_paused():
            if active_blocking_plugin is None:
                event = self.get_event_at_scenario_time(self.scenario_time)
                if event is not None:
                    self.execute_one_event(event)

            # Check if a blocking plugin has started so to pause concurrent plugins
            elif active_blocking_plugin.alive:
                # Toggle scenario_time pause only once
                if not self.is_scenario_time_paused():
                    self.pause_scenario()
                    self.paused_plugins = self.get_active_non_blocking_plugins()
                    self.execute_plugins_methods(self.paused_plugins, methods=['pause', 'hide'])

        # In Replay mode: IT IS the play/pause button that manages the scenario resuming
        elif active_blocking_plugin is None and REPLAY_MODE == False:
            if len(self.paused_plugins) > 0:
                self.execute_plugins_methods(self.paused_plugins, methods=['show', 'resume'])
                self.paused_plugins = list()
            self.resume_scenario()


    def is_scenario_time_paused(self):
        return self.pause_scenario_time == True


    def pause_scenario(self):
        self.pause_scenario_time = True
        return self.is_scenario_time_paused()


    def resume_scenario(self):
        self.pause_scenario_time = False
        return self.is_scenario_time_paused()


    def toogle_scenario(self):
        self.pause_scenario_time = not self.pause_scenario_time
        return self.is_scenario_time_paused()


    def get_active_blocking_plugin(self):
        # A blocking plugin must be alive to actually pause scenario progression.
        p = self.get_plugins_by_states([('alive', True), ('blocking', True), ('paused', False)])
        if len(p) > 0:
            return p[0]


    def get_active_non_blocking_plugins(self):
        return self.get_plugins_by_states([('blocking', False), ('paused', False)])


    def get_active_plugins(self):
        return self.get_plugins_by_states([('alive', True)])


    def execute_one_event(self, event):
        # Set the plugin corresponding to the event
        plugin = self.plugins[event.plugin]

        # If one argument, assume it is a plugin method to execute
        if len(event.command) == 1:
            getattr(plugin, event.command[0])()
            if (event.command[0] == 'start'
                    and event.plugin in self.core_task_plugins
                    and not self.start_signal_sent):
                self.win.imotions_bridge.on_task_start()
                self.start_signal_sent = True
            if (event.command[0] == 'show_summary'
                    and event.plugin == 'performance'
                    and not self.end_signal_sent):
                # Fire end signal exactly when performance summary appears.
                self.win.imotions_bridge.on_task_end()
                self.end_signal_sent = True

        # If two arguments in the 'command' field, it can be either a
        # parameter update (parameter;value) OR a method-with-argument
        # (method;arg). Prefer calling a plugin method if it exists.
        elif len(event.command) == 2:
            cmd_name, cmd_val = event.command[0], event.command[1]
            # If plugin exposes a callable with this name, call it with the arg
            if hasattr(plugin, cmd_name) and callable(getattr(plugin, cmd_name)):
                try:
                    getattr(plugin, cmd_name)(cmd_val)
                except TypeError:
                    # Fallback: if method signature differs, try without arg
                    try:
                        getattr(plugin, cmd_name)()
                    except Exception:
                        # As a last resort, set as parameter
                        getattr(plugin, 'set_parameter')(cmd_name, cmd_val)
            else:
                getattr(plugin, 'set_parameter')(cmd_name, cmd_val)

        event.done = 1

        # Utile ?
        # if self.replay_mode:
            # plugin.update(0)

        # The event can be logged whenever inside the method, since self.durations remain
        # constant all along it
        logger.record_event(event)


    def execute_plugins_methods(self, plugins, methods):
        if len(plugins) == 0:
            return

        if isinstance(methods, str):
            methods = [methods]

        for m in methods:
            for p in plugins:
                # self.execute_one_event(Event(0, 0, p.alias, m)) DO NOT create new events
                getattr(p, m)()


    def get_plugins_by_states(self, attribute_state_list):
        plugins = {k:p for k,p in self.plugins.items()}
        for (attribute, state) in attribute_state_list:
            plugins = {k:p for k,p in plugins.items() if getattr(p, attribute) == state}
        return [p for _,p in plugins.items()]


    def get_event_at_scenario_time(self, scenario_time: float):
        # Retrieve (simultaneous) events matching scenario_duration_sec
        # We look to the most precise point in the near future that might matches a set of event time(s)
        events_time = [event for event in self.events
                       if event.time_sec <= scenario_time]

        # Filter events that are either done or already in the queue
        events_time = [event for event in events_time
                       if event.done != 1]

        # Sort them according to their line number (ascending order)
        # and append the listed events in the correct order
        for event in sorted(events_time, key=lambda x: x.line):
            if event not in self.events_queue:
                self.events_queue.append(event)

        return self.unqueue_event()


    def reload_events_from_file(self):
        """Reload events from the scenario file path without re-instantiating plugins.
        This replaces the scheduler's event list while keeping plugin instances intact.
        """
        if not self.scenario_path:
            return
        try:
            with open(self.scenario_path, 'r', encoding='utf-8') as fh:
                lines = fh.readlines()
        except Exception:
            logger.log_manual_entry(f'Failed to read scenario file for reload: {self.scenario_path}', key='scenario_reload')
            return

        # Parse into Event objects (skip empty/comment lines)
        new_events = [Event.parse_from_string(line_n, line_str) for line_n, line_str
                      in enumerate(lines)
                      if len(line_str.strip()) > 0 and not line_str.startswith('#')]

        # Apply retrocompatibility and basic checks are skipped here to be lightweight.
        # Reset execution flags and replace events
        for e in new_events:
            e.done = 0
        self.events = new_events
        self.events_queue = []
        logger.log_manual_entry(f'Reloaded {len(self.events)} events from {self.scenario_path}', key='scenario_reload')


    def unqueue_event(self):
        # If some events must be executed, unstack the next event
        if len(self.events_queue) > 0:
            event = self.events_queue[0]
            del self.events_queue[0]
            return event

        return None


    def get_paused_tasks(self):
        """Return a list of task names that are currently paused via pause events"""
        paused = []
        for task_name in ['sysmon', 'track', 'communications']:
            if task_name in self.plugins:
                plugin = self.plugins[task_name]
                if plugin.paused:
                    paused.append(task_name)
        return paused


    def exit(self):
        logger.log_manual_entry('end')
        self.event_loop.exit()
        sys.exit(0)


    def run(self):
        self.event_loop.run()

import logging
import time

from dash_emulator.models import State
from dash_emulator.mpd import MPDProvider
from dash_emulator.player import PlayerEventListener
from dash_emulator.scheduler import SchedulerEventListener
from exp_common.exp_events import ExpEvent_Progress, ExpEvent_State
from exp_common.exp_recorder import ExpWriter


class EventLogger(SchedulerEventListener, PlayerEventListener):
    log = logging.getLogger("EventLogger")

    def __init__(self, mpd_provider: MPDProvider = None, recorder: ExpWriter = None):
        """
        Log events to console and events file
        Parameters
        ----------
        dump_events: file path to write events
        """
        self.recorder = recorder
        self._total_duration = None
        self.mpd_provider = mpd_provider

    @property
    def total_duration(self):
        if self._total_duration is None:
            self._total_duration = self.mpd_provider.mpd.max_segment_duration * \
                                   len(self.mpd_provider.mpd.adaptation_sets[0].representations[0].segments)
        return self._total_duration

    async def on_buffer_level_change(self, buffer_level):
        self.log.debug(f"Buffer level: {buffer_level:.3f}")

    async def on_position_change(self, position):
        progress = position / self.total_duration
        self.recorder.write_event(ExpEvent_Progress(round(time.time() * 1000), progress))

    async def on_state_change(self, position: float, old_state: State, new_state: State):
        self.log.info("Switch state. pos: %.3f, from %s to %s" % (position, old_state, new_state))
        progress = position / self.total_duration
        self.recorder.write_event(ExpEvent_State(round(time.time() * 1000), progress, str(old_state), str(new_state)))

    async def on_segment_download_start(self, index, selections):
        self.log.info("Download start. Index: %d, Selections: %s" % (index, str(selections)))

    async def on_segment_download_complete(self, index):
        self.log.info("Download complete. Index: %d" % index)

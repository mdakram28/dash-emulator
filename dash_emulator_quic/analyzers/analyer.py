import datetime
import io
import logging
import os
from abc import ABC, abstractmethod
from typing import List, Tuple, Union, TextIO

import matplotlib.pyplot as plt
from dash_emulator.bandwidth import BandwidthUpdateListener
from dash_emulator.models import State
from dash_emulator.mpd import MPDProvider
from dash_emulator.player import PlayerEventListener
from dash_emulator.scheduler import SchedulerEventListener


class PlaybackAnalyzer(ABC):
    @abstractmethod
    def save(self, output: TextIO) -> None:
        """
        Save results to output
        """


class BETAPlaybackAnalyzerConfig:
    def __init__(self, save_plots_dir=None):
        self.save_plots_dir = save_plots_dir


class BETAPlaybackAnalyzer(PlaybackAnalyzer, PlayerEventListener, SchedulerEventListener,
                           BandwidthUpdateListener):
    log = logging.getLogger("BETAPlaybackAnalyzer")

    def __init__(self, config: BETAPlaybackAnalyzerConfig, mpd_provider: MPDProvider):
        self.config = config
        self._mpd_provider = mpd_provider
        self._start_time = datetime.datetime.now().timestamp()
        self._buffer_levels: List[Tuple[float, float]] = []
        self._throughputs: List[Tuple[float, int]] = []
        self._states: List[Tuple[float, State]] = []
        self._segments: List[
            Tuple[float, float, int, int]] = []  # start time, completion time, quality selection, bandwidth

        # index, start time, completion time, quality, bandwidth
        self._current_segment: List[Union[int, float]] = [0, 0, 0, 0, 0]

    @staticmethod
    def _seconds_since(start_time: float):
        """
        Calculate the seconds since a given time

        Parameters
        ----------
        start_time:
            The start time in seconds

        Returns
        -------
        The seconds sice given start_time

        """
        return datetime.datetime.now().timestamp() - start_time

    async def on_state_change(self, position: float, old_state: State, new_state: State):
        self._states.append((self._seconds_since(self._start_time), new_state))

    async def on_buffer_level_change(self, buffer_level):
        self._buffer_levels.append((self._seconds_since(self._start_time), buffer_level))

    async def on_segment_download_start(self, index, selections):
        if len(self._throughputs) != 0:
            self._current_segment = [index, self._seconds_since(self._start_time), None, selections[0],
                                     self._throughputs[-1][1]]
        else:
            self._current_segment = [index, self._seconds_since(self._start_time), None, selections[0], 0]

    async def on_segment_download_complete(self, index):
        completion_time = self._seconds_since(self._start_time)
        self._current_segment[2] = completion_time

        index, start_time, _, selection, throughput = self._current_segment

        self._segments.append((start_time, completion_time, selection, throughput))
        assert len(self._segments) == index + 1

    async def on_bandwidth_update(self, bw: int) -> None:
        self._throughputs.append((self._seconds_since(self._start_time), bw))

    def _get_video_bitrate(self, representation_id):
        """
        Get the video bitrate of given representation id

        Parameters
        ----------
        representation_id:
            The representation ID of the info

        Returns
        -------
        The video bitrate of given representation id

        """
        mpd = self._mpd_provider.mpd
        adaptation_set = None

        if len(mpd.adaptation_sets) != 1:
            return 0

        for adaptation_set_id, adaptation_set_obj in mpd.adaptation_sets.items():
            if adaptation_set_obj.content_type == 'video':
                adaptation_set = adaptation_set_obj
                break

        if adaptation_set is None:
            return 0

        representation = adaptation_set.representations[representation_id]
        return representation.bandwidth if representation is not None else 0

    def save(self, output: io.TextIOBase) -> None:
        bitrates = []

        last_quality = None
        quality_switches = 0

        output.write("%-10s%-10s%-10s%-10s%-10s%-10s\n" % ('Index', 'Start', 'End', 'Quality', 'Bitrate', 'Throughput'))
        for index, segment in enumerate(self._segments):
            start, end, selection, throughput = segment
            if last_quality is None:
                # First segment
                last_quality = selection
            else:
                if last_quality != selection:
                    last_quality = selection
                    quality_switches += 1
            bitrate = self._get_video_bitrate(selection)
            bitrates.append(bitrate)
            output.write("%-10d%-10.2f%-10.2f%-10d%-10d%-10d\n" % (index, start, end, selection, bitrate, throughput))
        output.write("\n")

        # Stalls
        output.write("Stalls:\n")
        output.write("%-6s%-6s%-6s\n" % ("Start", "End", "Duration"))
        buffering_start = None
        for time, state in self._states:
            if state == State.BUFFERING:
                buffering_start = time
            elif state == State.READY:
                if buffering_start is not None:
                    output.write("%-6.2f%-6.2f%-6.2f\n" % (buffering_start, time, time - buffering_start))
                    buffering_start = None

        # Average bitrate
        output.write('\n')
        average_bitrate = sum(bitrates) / len(bitrates)
        output.write(f"Average bitrate: {average_bitrate:.2f} bps\n")

        # Number of quality switches
        output.write('\n')
        output.write(f"Number of quality switches: {quality_switches}\n")

        if self.config.save_plots_dir is not None:
            self.save_plot()

    def save_plot(self):
        def plot_bws(ax: plt.Axes):
            xs = [i[0] for i in self._throughputs]
            ys = [i[1] / 1000 for i in self._throughputs]
            lines1 = ax.plot(xs, ys, color='red', label='Throughput')
            ax.set_xlim(0)
            ax.set_ylim(0)
            ax.set_xlabel("Time (second)")
            ax.set_ylabel("Bandwidth (kbps)", color='red')
            return *lines1,

        def plot_bufs(ax: plt.Axes):
            xs = [i[0] for i in self._buffer_levels]
            ys = [i[1] for i in self._buffer_levels]
            line1 = ax.plot(xs, ys, color='blue', label='Buffer')
            ax.set_xlim(0)
            ax.set_ylim(0)
            ax.set_ylabel("Buffer (second)", color='blue')
            line2 = ax.hlines(1.5, 0, 20, linestyles='dashed', label='Panic buffer')
            return *line1, line2

        output_file = os.path.join(self.config.save_plots_dir, "status.pdf")
        fig: plt.Figure
        ax1: plt.Axes
        fig, ax1 = plt.subplots()
        ax2: plt.Axes = ax1.twinx()
        lines = plot_bws(ax1) + plot_bufs(ax2)
        labels = [line.get_label() for line in lines]
        fig.legend(lines, labels)
        fig.savefig(output_file)

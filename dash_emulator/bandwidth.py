import logging
import operator
import time
from abc import ABC, abstractmethod
from typing import List

from dash_emulator.download import DownloadEventListener


class BandwidthUpdateListener(ABC):
    @abstractmethod
    async def on_bandwidth_update(self, bw: int, extra_stats: dict) -> None:
        """
        Parameters
        ----------
        bw: int
            The latest bandwidth estimate in bps (bytes per second)
        """
        pass

    @abstractmethod
    async def on_continuous_bw_update(self, bw: int) -> None:
        """
        Parameters
        ----------
        bw: int
            The instantaneous latest bandwidth estimate in bps (bytes per second)
        update_time: float
            The time at which this bandwidth is estimated
        """

class BandwidthMeter(ABC):
    @property
    @abstractmethod
    def bandwidth(self) -> int:
        """
        Returns
        -------
        bw: int
            The bandwidth estimate in bps (bytes per second)
        """
        pass

    @abstractmethod
    def add_listener(self, listener: BandwidthUpdateListener):
        """
        Add a listener to the bandwidth meter

        Parameters
        ----------
        listener
            An instance of BandwidthUpdateListener
        """
        pass


class BandwidthMeterImpl(BandwidthMeter, DownloadEventListener):
    log = logging.getLogger("BandwidthMeterImpl")

    def __init__(self, init_bandwidth: int, smooth_factor: float,
                 bandwidth_update_listeners: List[BandwidthUpdateListener],
                 cont_bw_window: int = 1, max_packet_delay: float = 10):
        """
        The formula to estimate the bandwidth is
            bandwidth = last_bandwidth * smooth_factor + latest_bandwidth * (1-smooth_factor)

        Parameters
        ----------
        init_bandwidth: int
            The initial bandwidth in bps (bytes per second)
        smooth_factor : float
            The smooth factor in use.
        bandwidth_update_listeners: List[BandwidthUpdateListener]
            A list of bandwidth update listeners
        """
        self.last_byte_at = 0
        self._bw = init_bandwidth
        self.smooth_factor = smooth_factor
        self.listeners = bandwidth_update_listeners

        self.bytes_transferred = 0
        self.transmission_start_time = None
        self.transmission_end_time = None
        self.extra_stats = {}
        self.first_byte_in_segment = True
        self._cont_bw = []
        self.cont_bw_window = cont_bw_window
        self.last_cont_bw = None
        self.max_packet_delay = max_packet_delay
        self.downloading_url = None

    async def on_transfer_start(self, url) -> None:
        self.transmission_start_time = time.time()
        self.bytes_transferred = 0
        self.first_byte_in_segment = True
        self.downloading_url = url
        self.log.info("Transmission starts. URL: " + url)

    async def on_bytes_transferred(self, length: int, url: str, position: int, size: int, content) -> None:
        # if url == self.downloading_url:
        self.bytes_transferred += length
        t = time.time()
        await self.update_cont_bw(length, t)
        
        # self.log.info(f"Transferred : {length} bytes")
        # if self.first_byte_at is None:
        #     self.first_byte_at = t
        # self.last_byte_at = t

    async def on_transfer_end(self, size: int, url: str) -> None:
        self.transmission_end_time = time.time()
        self.update_bandwidth()
        self.bytes_transferred = 0

        for listener in self.listeners:
            await listener.on_bandwidth_update(self._bw, self.extra_stats)

    async def on_transfer_canceled(self, url: str, position: int, size: int) -> None:
        return await self.on_transfer_end(position, url)

    @property
    def bandwidth(self) -> int:
        return self._bw

    async def update_cont_bw(self, bytes_transferred: int, time_at: float):
        min_values = 2
        if self.first_byte_in_segment:
            self.first_byte_in_segment = False
        else:
            est_bw = 8*bytes_transferred/(time_at - self.last_byte_at)
            # if est_bw < 10000000000:
            # if self.max_packet_delay > (time_at - self.last_byte_at) > 0.001:
            if True:
                self._cont_bw.append((self.last_byte_at, time_at, bytes_transferred))
                if len(self._cont_bw) >= min_values:
                    window_start = time_at - self.cont_bw_window
                    window_values = []
                    for bw in self._cont_bw[::-1]:
                        if bw[1] < window_start and len(window_values) >= min_values:
                            break
                        window_values.append(bw)
                    # window = self._cont_bw[max(0, len(self._cont_bw)-self.rolling_mean_window):]
                    total_bytes = sum(list(map(operator.itemgetter(2), window_values)))
                    total_time = sum(list(map(lambda bw: (bw[1]-bw[0]), window_values)))
                    window_mean = int(8*total_bytes/total_time)
                    self.last_cont_bw = window_mean
        for listener in self.listeners:
            await listener.on_continuous_bw_update(self.last_cont_bw)
        self.last_byte_at = time_at


    def update_bandwidth(self):
        self._bw = self._bw * self.smooth_factor + \
                   (8 * self.bytes_transferred) / (self.transmission_end_time - self.transmission_start_time) * \
                   (1 - self.smooth_factor)
        # if self.last_cont_bw is not None:
        #     self._bw = (self._bw + self.last_cont_bw)/2
            # self._bw = self.last_cont_bw
        self.extra_stats = {
            "_bw": self._bw,
            "smooth_factor": self.smooth_factor,
            "bytes_transferred": self.bytes_transferred,
            "transmission_end_time": self.transmission_end_time,
            "transmission_start_time": self.transmission_start_time
        }
        self.log.info(f"************* Updated stats : {self.extra_stats}")

    def add_listener(self, listener: BandwidthUpdateListener):
        if listener not in self.listeners:
            self.listeners.append(listener)

import asyncio
import datetime
import logging
from abc import abstractmethod
from typing import Optional

from dash_emulator.bandwidth import BandwidthUpdateListener
from dash_emulator.download import DownloadEventListener, DownloadManager
from dash_emulator.mpd import MPDProvider
from dash_emulator.player import PlayerEventListener
from dash_emulator.scheduler import SchedulerEventListener
from dash_emulator.service import AsyncService

from dash_emulator_quic.beta.events import *
from dash_emulator_quic.beta.vq_threshold import VQThresholdManager
from dash_emulator_quic.models import SegmentRequest


class BETAManager(AsyncService):
    @abstractmethod
    async def start(self):
        """
        Start the BETA Manager
        """
        pass


class BETAManagerImpl(BETAManager, DownloadEventListener, PlayerEventListener, SchedulerEventListener,
                      BandwidthUpdateListener):
    log = logging.getLogger("BETAManagerImpl")

    MIN_REF_RATIO = 0.4

    def __init__(self,
                 mpd_provider: MPDProvider,
                 download_manager: DownloadManager,
                 vq_threshold_manager: VQThresholdManager,
                 panic_buffer_level: float):
        """
        The constructor will create a asyncio.Queue.
        Be sure to create this instance inside an event loop.

        Parameters
        ----------
        mpd_provider
            The MPD provider which could provides the latest MPD contents
        download_manager
            The download manager
        """
        self.mpd_provider = mpd_provider
        self.download_manager = download_manager
        self.vq_threshold_manager = vq_threshold_manager
        self.panic_buffer_level = panic_buffer_level

        self._event_queue: asyncio.Queue[BETAEvent] = asyncio.Queue()

        self._bw = 0
        self._buffer_level = 0
        self._state: Optional[State] = None

        self._current_segment: Optional[SegmentRequest] = None
        self._pending_segment: Optional[SegmentRequest] = None

        self._timeout = -1
        self._max_timeout = -1

    async def on_bytes_transferred(self, length: int, url: str, position: int, size: int) -> None:
        await self._event_queue.put(BytesTransferredEvent(length, url, position, size))

    async def on_transfer_end(self, size: int, url: str) -> None:
        await self._event_queue.put(TransferEndEvent(size, url))

    async def on_transfer_start(self, url) -> None:
        await self._event_queue.put(TransferStartEvent(url))

    async def on_transfer_canceled(self, url: str, position: int, size: int) -> None:
        await self._event_queue.put(TransferCancelEvent(url, position, size))

    async def on_state_change(self, position: float, old_state: State, new_state: State):
        await self._event_queue.put(StateChangeEvent(new_state))

    async def on_buffer_level_change(self, buffer_level):
        await self._event_queue.put(BufferLevelChangeEvent(buffer_level))

    async def on_segment_download_start(self, index, selections):
        await self._event_queue.put(SegmentDownloadStartEvent(index, selections))

    async def on_segment_download_complete(self, index):
        await self._event_queue.put(SegmentDownloadCompleteEvent(index))

    async def on_bandwidth_update(self, bw: int) -> None:
        await self._event_queue.put(BandwidthUpdateEvent(bw))

    async def start(self):
        while True:
            event = await self._event_queue.get()
            await self._process(event)

    async def _process(self, event: BETAEvent):
        if isinstance(event, BandwidthUpdateEvent):
            # Update the bandwidth
            self._bw = event.bw
        elif isinstance(event, BufferLevelChangeEvent):
            self._buffer_level = event.buffer_level
        elif isinstance(event, StateChangeEvent):
            self._state = event.state
        elif isinstance(event, SegmentDownloadStartEvent):
            await self._segment_download_start(event)
        elif isinstance(event, TransferStartEvent):
            await self._transfer_start(event)
        elif isinstance(event, BytesTransferredEvent):
            await self._bytes_transferred(event)

    async def _segment_download_start(self, event: SegmentDownloadStartEvent):
        self._current_segment = SegmentRequest(event.index, None)

        # The bandwidth is not updated. It's the first segment. Do not apply BETA algorithm on it
        if self._bw == 0:
            return

    async def _transfer_start(self, event: TransferStartEvent):
        self._current_segment.url = event.url

    async def _bytes_transferred(self, event: BytesTransferredEvent):
        """
        First packet comes in.
        If there is a pending segment, cancel that segment request
        """
        if self._pending_segment is not None and not self._pending_segment.canceled:
            self.log.debug(f"BETA: has pending segment of index {self._pending_segment.index}, stop downloading")
            self._pending_segment.canceled = True
            await self.download_manager.stop(self._pending_segment.url)

        if self._state != State.READY:
            return

        if self._current_segment.first_bytes_received is False:
            self._current_segment.first_bytes_received = True
            timeout_value = (event.size - event.length) * 8 / self._bw
            max_timeout_value = timeout_value * 2
            self.log.debug(f"BETA: BETA calculate timeout: {timeout_value}, max timeout {max_timeout_value}")
            self._timeout = datetime.datetime.now() + datetime.timedelta(seconds=timeout_value)
            self._max_timeout = datetime.datetime.now() + datetime.timedelta(seconds=max_timeout_value)
            return

        now = datetime.datetime.now()
        if now < self._timeout:
            return

        ratio = event.position / event.size
        if ratio < self.MIN_REF_RATIO:
            return

        if ratio > self.vq_threshold_manager.get_threshold(self._current_segment.index):
            await self._stop_download()
            return

        if self._buffer_level < self.panic_buffer_level:
            await self._stop_download()
            return

        if now > self._max_timeout and ratio > self.MIN_REF_RATIO:
            await self._stop_download()
            return

    async def _stop_download(self):
        pass

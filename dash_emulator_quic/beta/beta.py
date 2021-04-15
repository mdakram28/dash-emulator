import asyncio
import logging
from abc import abstractmethod
from typing import Optional

from dash_emulator.bandwidth import BandwidthUpdateListener
from dash_emulator.download import DownloadEventListener, DownloadManager
from dash_emulator.models import State
from dash_emulator.mpd import MPDProvider
from dash_emulator.player import PlayerEventListener
from dash_emulator.scheduler import SchedulerEventListener
from dash_emulator.service import AsyncService

from dash_emulator_quic.beta.events import BandwidthUpdateEvent, BETAEvent, BufferLevelChangeEvent, StateChangeEvent, \
    SegmentDownloadStartEvent, SegmentDownloadCompleteEvent, BytesTransferredEvent, TransferEndEvent, \
    TransferStartEvent, TransferCancelEvent


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

    def __init__(self, mpd_provider: MPDProvider, download_manager: DownloadManager):
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

        self._queue: asyncio.Queue[BETAEvent] = asyncio.Queue()

        self._bw = 0
        self._buffer_level = 0
        self._state: Optional[State] = None

    async def on_bytes_transferred(self, length: int, url: str, position: int, size: int) -> None:
        await self._queue.put(BytesTransferredEvent(length, url, position, size))

    async def on_transfer_end(self, size: int, url: str) -> None:
        await self._queue.put(TransferEndEvent(size, url))

    async def on_transfer_start(self, url) -> None:
        await self._queue.put(TransferStartEvent(url))

    async def on_transfer_canceled(self, url: str, position: int, size: int) -> None:
        await self._queue.put(TransferCancelEvent(url, position, size))

    async def on_state_change(self, position: float, old_state: State, new_state: State):
        await self._queue.put(StateChangeEvent(new_state))

    async def on_buffer_level_change(self, buffer_level):
        await self._queue.put(BufferLevelChangeEvent(buffer_level))

    async def on_segment_download_start(self, index, selections):
        await self._queue.put(SegmentDownloadStartEvent(index, selections))

    async def on_segment_download_complete(self, index):
        await self._queue.put(SegmentDownloadCompleteEvent(index))

    async def on_bandwidth_update(self, bw: int) -> None:
        await self._queue.put(BandwidthUpdateEvent(bw))

    async def start(self):
        while True:
            event = await self._queue.get()
            await self._process(event)

    async def _process(self, event: BETAEvent):
        if isinstance(event, BandwidthUpdateEvent):
            # Update the bandwidth
            self._bw = event.bw
        elif isinstance(event, BufferLevelChangeEvent):
            self._buffer_level = event.buffer_level
        elif isinstance(event, StateChangeEvent):
            self._state = event.state

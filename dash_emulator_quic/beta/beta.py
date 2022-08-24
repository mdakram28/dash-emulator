import asyncio
import datetime
import logging
from abc import abstractmethod
from typing import Optional

from dash_emulator.bandwidth import BandwidthUpdateListener
from dash_emulator.download import DownloadEventListener, DownloadType
from dash_emulator.mpd import MPDProvider
from dash_emulator.player import PlayerEventListener
from dash_emulator.scheduler import SchedulerEventListener
from dash_emulator.service import AsyncService

from dash_emulator_quic.beta.events import *
from dash_emulator_quic.beta.vq_threshold import VQThresholdManager
from dash_emulator_quic.models import SegmentRequest
from dash_emulator_quic.downloader.client import QuicClient


class BETAManager(AsyncService):
    @abstractmethod
    async def start(self):
        """
        Start the BETA Manager
        """
        pass


class BETAManagerImpl(BETAManager, DownloadEventListener, PlayerEventListener, SchedulerEventListener,
                      BandwidthUpdateListener):

    async def on_position_change(self, position):
        pass

    log = logging.getLogger("BETAManagerImpl")

    MIN_REF_RATIO = 0.6

    def __init__(self,
                 mpd_provider: MPDProvider,
                 download_manager: QuicClient,
                 vq_threshold_manager: VQThresholdManager,
                 panic_buffer_level: float,
                 safe_buffer_level: float):
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
        self.safe_buffer_level = safe_buffer_level

        self._event_queue: asyncio.Queue[BETAEvent] = asyncio.Queue()

        self._bw = 0
        self._buffer_level = 0
        self._state: Optional[State] = None

        self._current_segment: Optional[SegmentRequest] = None
        self._pending_segment: Optional[SegmentRequest] = None

        self._timeout = -1
        self._max_timeout = -1

        self._dropped_urls = set()
        self._dropped_indices = set()
        self.ratio = 0

        self.beta_loop_task = None

        # self.log.setLevel(logging.DEBUG)

    async def on_bytes_transferred(self, length: int, url: str, position: int, size: int, content) -> None:
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

    async def on_bandwidth_update(self, bw: int, extra_args: dict) -> None:
        await self._event_queue.put(BandwidthUpdateEvent(bw))

    async def on_continuous_bw_update(self, bw: int) -> None:
        pass

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
        self.ratio = 0

        # The bandwidth is not updated. It's the first segment. Do not apply BETA algorithm on it
        if self._bw == 0:
            return

    async def _transfer_start(self, event: TransferStartEvent):
        self.log.info(f"Start downloading {event.url}")
        self._current_segment.url = event.url

        # if self.beta_loop_task is None:
        #     self.beta_loop_task = asyncio.create_task(self.beta_loop())

    # async def beta_loop(self):
    #     self.log.info("BETA loop start")
    #     try:
    #         while self._state != State.END:
    #             await asyncio.sleep(0.2)
    #             await self.stop_download_if_needed()
    #     except asyncio.CancelledError:
    #         self.log.info("BETA loop task cancelled")
    #         raise

    async def _bytes_transferred(self, event: BytesTransferredEvent):
        """
        First packet comes in.
        If there is a pending segment, cancel that segment request
        """
        self.log.info(f"Bytes received ({event.position}/{event.size}) {event.url}")
        if self._pending_segment is not None and event.url != self._pending_segment.url:
            self.log.info(f"Cancel pending segment {self._pending_segment.url}")
            self.download_manager.cancel_read_url(self._pending_segment.url)
            self._pending_segment = None
        elif self._pending_segment is not None and self._pending_segment.url == event.url:
            # self.log.info(f"Received pending segment of {event.size} bytes for {event.url.split('/')[-1]}")
            return

        download_type = DownloadType.SEGMENT
        if event.url.split("/")[-1].startswith("init"):
            download_type = DownloadType.STREAM_INIT

        if download_type == DownloadType.STREAM_INIT:
            return

        if self._buffer_level > self.safe_buffer_level:
            return

        # If the segment is a dropped url, ignore it
        if event.url in self._dropped_urls:
            return
        # If the index is a dropped index, but the url is diffe     rent, it means it's the replacing segment, do nothing.
        if self._current_segment.index in self._dropped_indices:
            return

        self.log.debug(f"current_segment.first_bytes_received = {self._current_segment.first_bytes_received}")
        if self._current_segment.first_bytes_received is False:
            # This happens when a new quality stream init file is downloaded
            if event.size == event.length:
                return
            self._current_segment.first_bytes_received = True
            try:
                self.log.info(f"event.size={event.size}, event.length={event.length}, self._bw={self._bw} url={event.url}")
                timeout_value = (event.size - event.length) * 8 / (self._bw*0.7)
                # timeout_value = (event.size - event.length) * 8 / self._bw
            except ZeroDivisionError:
                timeout_value = 10
            max_timeout_value = timeout_value * 2
            self.log.info(f"BETA: BETA calculate timeout: {timeout_value}, max timeout {max_timeout_value}")
            self._timeout = datetime.datetime.now() + datetime.timedelta(seconds=timeout_value)
            self._max_timeout = datetime.datetime.now() + datetime.timedelta(seconds=max_timeout_value)
            return

        now = datetime.datetime.now()
        self.ratio = event.position / event.size

        if self.ratio > 0.99:
            return

        self.log.info(f"state={self._state}, ratio={self.ratio}, MIN_REF_RATIO={self.MIN_REF_RATIO}")

        if self._current_segment.index != 0 and event.url == self._current_segment.url and self._state == State.BUFFERING and self.ratio > self.MIN_REF_RATIO:
            self.log.info(f"Stopping download. Reason: started buffering")
            await self._stop_download()
            return

        self.log.debug(f"buffer_level={self._buffer_level}, panic_buffer_level={self.panic_buffer_level}")
        # if ratio > self.MIN_REF_RATIO and self._buffer_level < self.panic_buffer_level:
        #     await self._stop_download()
        #     return

        self.log.debug(f"_timeout={self._timeout}, _max_timeout={self._max_timeout}, panic_buffer_level={self.panic_buffer_level}")
        if now < self._timeout:
            return

        vq_threshold = self.vq_threshold_manager.get_threshold(self._current_segment.index)
        self.log.info(f"ratio={self.ratio}, vq_threshold={vq_threshold}")
        if self.ratio > vq_threshold:
            # await self._stop_download()
            self.log.info(f"Stopping download. Reason: ratio={self.ratio} exceeded vq_threshold={vq_threshold}")
            await self._stop_download()
            return

        if self._buffer_level < self.panic_buffer_level:
            self.log.info(f"Stopping download. Reason: buffer_level={self._buffer_level} < panic_buffer_level={self.panic_buffer_level}")
            if self.ratio < self.MIN_REF_RATIO:
                # await self.drop_and_replace()
                # await self._stop_download()
                pass
            else:
                await self._stop_download()
            return

        self.log.info(f"Stopping download. Reason: timeout exceeded")
        if now > self._max_timeout and self.ratio > self.MIN_REF_RATIO:
            # await self.drop_and_replace()
            await self._stop_download()
            return
        # else:
        #     await self._stop_download()
        #     return

    async def _stop_download(self):
        try:
            if self._pending_segment is None or self._pending_segment.url != self._current_segment.url:
                await self.download_manager.stop(self._current_segment.url)
        finally:
            self._pending_segment = self._current_segment
            self.log.info(f"BETA: Stopped Downloading: {self._current_segment.url}")

    async def drop_and_replace(self):
        self.log.info(f"BETA: Drop URL: {self._current_segment.url} and replace with the lowest bitrate")
        self._dropped_urls.add(self._current_segment.url)
        self._dropped_indices.add(self._current_segment.index)
        await self.download_manager.drop_url(self._current_segment.url)
        self.download_manager.cancel_read_url(self._current_segment.url)

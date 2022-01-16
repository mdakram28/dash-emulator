import asyncio
import logging
from typing import Optional, Tuple, List

import aiohttp
from dash_emulator.download import DownloadEventListener

from dash_emulator_quic.downloader.client import QuicClient


class TCPClientImpl(QuicClient):
    log = logging.getLogger("TCPClientImpl")

    def __init__(self, event_listeners: List[DownloadEventListener]):
        self._event_listeners = event_listeners
        self._download_queue = asyncio.Queue()
        self._session = None
        self._session_close_event = asyncio.Event()
        self._download_finish_event = asyncio.Event()
        self._is_busy = False
        self._downloading_task = None  # type: Optional[asyncio.Task]
        self._content = bytearray()
        self._headers = None
        self._completed_urls = set()

    async def wait_complete(self, url: str) -> Optional[Tuple[bytes, int]]:
        await self._download_finish_event.wait()
        return bytes(self._content), int(self._headers['CONTENT-LENGTH'])

    def cancel_read_url(self, url: str):
        return

    async def drop_url(self, url: str):
        await self.stop(url)

    @property
    def is_busy(self):
        return self._is_busy

    async def download(self, url, save: bool = False) -> Optional[bytes]:
        if self._session is None:
            session_start_event = asyncio.Event()
            asyncio.create_task(self._create_session(session_start_event))
            await session_start_event.wait()

        for listener in self._event_listeners:
            await listener.on_transfer_start(url)
        await self._download_queue.put(url)
        return None

    async def _download_inner(self, url):
        self._content = bytearray()
        self._download_finish_event.clear()
        async with self._session.get(url) as resp:
            self._headers = resp.headers
            async for chunk in resp.content.iter_chunked(10240):
                self._content += bytearray(chunk)
                for listener in self._event_listeners:
                    await listener.on_bytes_transferred(len(chunk), url, len(self._content), int(resp.headers['CONTENT-LENGTH']))
        self._download_finish_event.set()
        for listener in self._event_listeners:
            await listener.on_transfer_end(len(self._content), url)

    async def _download_task(self):
        while True:
            self._is_busy = False
            req_url = await self._download_queue.get()
            self._is_busy = True

            self._downloading_task = asyncio.create_task(self._download_inner(req_url))
            await self._download_finish_event.wait()
            self._downloading_task = None

    async def _create_session(self, session_start_event):
        async with aiohttp.ClientSession() as session:
            self._session = session
            session_start_event.set()
            task = asyncio.create_task(self._download_task())
            await self._session_close_event.wait()
            task.cancel()

    async def close(self):
        if self._session_close_event is not None:
            self._session_close_event.set()

    async def stop(self, url: str):
        if self._downloading_task is not None:
            self._downloading_task.cancel()
        self._download_finish_event.set()
        for listener in self._event_listeners:
            await listener.on_transfer_canceled(url, len(self._content), int(self._headers['CONTENT-LENGTH']))

    def add_listener(self, listener: DownloadEventListener):
        self._event_listeners.append(listener)

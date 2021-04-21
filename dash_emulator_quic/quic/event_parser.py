import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, cast, Set

from aioquic.h3.events import H3Event, HeadersReceived, DataReceived
from dash_emulator.download import DownloadEventListener


class H3EventParser(ABC):
    @abstractmethod
    async def wait_complete(self, url: str) -> Tuple[bytes, int]:
        pass

    @abstractmethod
    async def parse(self, url: str, event: H3Event):
        pass

    @abstractmethod
    def add_listener(self, listener: DownloadEventListener):
        pass

    @abstractmethod
    async def close_stream(self, url: str):
        pass


class H3EventParserImpl(H3EventParser):
    log = logging.getLogger("H3EventParserImpl")

    def __init__(self, listeners: List[DownloadEventListener] = None):
        self.listeners = listeners if listeners is not None else []

        self._completed_urls = set()
        self._waiting_urls: Dict[str, asyncio.Event] = dict()
        self._content_lengths: Dict[str, int] = dict()
        self._contents: Dict[str, bytearray] = dict()
        self._partially_accepted_urls: Set[str] = set()

    @staticmethod
    def parse_headers(headers: List[Tuple[bytes, bytes]]) -> Dict[str, str]:
        result = dict()
        for header in headers:
            key, value = header
            result[key.decode('utf-8')] = value.decode('utf-8')
        return result

    async def wait_complete(self, url: str) -> Tuple[bytes, int]:
        if url in self._partially_accepted_urls:
            content = self._contents[url]
            return bytes(content), self._content_lengths[url]
        if url not in self._completed_urls:
            self._waiting_urls[url] = asyncio.Event()
            await self._waiting_urls[url].wait()
            del self._waiting_urls[url]
        if url in self._completed_urls:
            self._completed_urls.remove(url)
        content = self._contents[url]
        size = self._content_lengths[url]
        del self._contents[url]
        del self._content_lengths[url]
        return bytes(content), size

    async def parse(self, url: str, event: H3Event):
        self.log.debug(f"Event received for {url}")
        if isinstance(event, HeadersReceived):
            headers = self.parse_headers(event.headers)
            size = int(headers.get("content-length"))
            self._content_lengths[url] = size
        else:
            event = cast(DataReceived, event)
            size = self._content_lengths[url]

            if url not in self._contents:
                self._contents[url] = bytearray()

            self._contents[url].extend(event.data)
            position = len(self._contents[url])

            for listener in self.listeners:
                await listener.on_bytes_transferred(len(event.data), url, position, size)

            if url in self._partially_accepted_urls:
                return

            if size == position:
                self._completed_urls.add(url)
                if url in self._waiting_urls:
                    self._waiting_urls[url].set()
                for listener in self.listeners:
                    await listener.on_transfer_end(size, url)

    def add_listener(self, listener: DownloadEventListener):
        self.listeners.append(listener)

    async def close_stream(self, url: str):
        self._partially_accepted_urls.add(url)
        if url in self._waiting_urls:
            self._waiting_urls[url].set()

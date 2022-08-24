import asyncio
import logging
import ssl
import traceback
from asyncio import Task
from typing import List, Optional, Tuple, Set, AsyncIterator, Dict
from urllib.parse import urlparse

from aioquic.asyncio import connect
from aioquic.h3.connection import H3_ALPN
from aioquic.h3.events import H3Event
from aioquic.quic.configuration import QuicConfiguration
from aioquic.tls import SessionTicket
from dash_emulator.download import DownloadEventListener

from dash_emulator_quic.downloader.client import QuicClient
from dash_emulator_quic.downloader.quic.event_parser import H3EventParser
from dash_emulator_quic.downloader.quic.protocol import HttpProtocol


class QuicClientImpl(QuicClient):
    """
    QuickClientImpl will use only one thread, but be multiplexing by tuning a queue
    """

    log = logging.getLogger("QuicClientImplV2")

    def __init__(self,
                 event_listeners: List[DownloadEventListener],
                 event_parser: H3EventParser,
                 session_ticket: Optional[SessionTicket] = None,
                 ssl_keylog_file: str = None
                 ):
        """
        Parameters
        ----------
        event_listeners: List[DownloadEventListener]
            A list of event listeners
        event_parser:
            Parse the H3Events
        session_ticket : SessionTicket, optional
            The ticket containing the authentication information.
            With this ticket, The QUIC Client can have 0-RTT on the first request (if the server allows).
            The QUIC Client will use 0-RTT for the following requests no matter if this parameter is provided.
        """
        self.event_parser = event_parser
        self.event_listeners = event_listeners
        self.ssl_keylog_file = ssl_keylog_file

        self._clients: Dict[str, HttpProtocol] = {}
        self._download_tasks: Dict[str, Task] = {}
        self._download_loop_task: Task = None

        self._close_event: Optional[asyncio.Event] = None
        """
        When this _close_event got set, the client will stop the connection completely.
        """

        self._canceled_urls: Set[str] = set()
        self._download_queue: Optional[asyncio.Queue[(str, int)]] = asyncio.Queue()

    @property
    def is_busy(self):
        """
        QUIC supports multiple streams in the same connection.
        It will be never busy because you can add a new request at any moment.

        Returns
        -------
        is_busy: bool
            False
        """
        return False

    async def wait_complete(self, url) -> Optional[Tuple[bytes, int]]:
        return await self.event_parser.wait_complete(url)

    async def close(self):
        # This is to close the whole connection
        self.log.info("Closing all connections")
        if self._close_event is not None:
            self._close_event.set()
        self._download_queue = None
        # self._download_loop_task.cancel()
        for url, download_task in self._download_tasks.items():
            download_task.cancel()

    async def stop(self, url: str):
        # This is to stop only one stream
        self.log.info(f"Cancelling download task {url}")
        if url in self._clients:
            # self._download_tasks[url].cancel()
            self._clients[url].close()
            await self.event_parser.close_stream(url)
            self.log.info(f"Cancelled download task {url}")


    async def _download_internal(self, url: str, rate: int) -> AsyncIterator[Tuple[H3Event, str]]:
        self.log.info(f"Downloading Internal: {url}")
        quic_configuration = QuicConfiguration(
            alpn_protocols=H3_ALPN,
            is_client=True,
            verify_mode=ssl.CERT_NONE,
            secrets_log_file=open(self.ssl_keylog_file, 'a')
        )
        parsed = urlparse(url)
        host = parsed.hostname
        if parsed.port is not None:
            port = parsed.port
        else:
            port = 443

        def save_session_ticket(ticket: SessionTicket) -> None:
            """
            Callback which is invoked by the TLS engine when a new session ticket
            is received.
            """
            self.log.info("New session ticket received from server: " + ticket.server_name)
            quic_configuration.session_ticket = ticket

        try:
            async with connect(
                    host,
                    port,
                    configuration=quic_configuration,
                    create_protocol=HttpProtocol,
                    session_ticket_handler=save_session_ticket,
                    local_port=0,
                    wait_connected=False,
            ) as client:
                self._clients[url] = client
                for listener in self.event_listeners:
                    await listener.on_transfer_start(url)
                async for event in self._clients[url].get(url):
                    asyncio.create_task(self.event_parser.parse(url, event))
                del self._clients[url]
        except:
            del self._clients[url]
            raise

    async def _download_loop(self):
        while True:
            req_url, rate = await self._download_queue.get()
            self.log.info(f"Received new request : {req_url}")
            self._download_tasks[req_url] = asyncio.create_task(self._download_internal(req_url, rate))


    async def download(self, url: str, save=False, rate=None) -> Optional[bytes]:
        if self._download_loop_task is None:
            self._download_loop_task = asyncio.create_task(self._download_loop())
        self.log.info(f"Queued new request : {url}")
        await self._download_queue.put((url, rate))
        return None

    def add_listener(self, listener: DownloadEventListener):
        if listener not in self.event_listeners:
            self.event_listeners.append(listener)

    def cancel_read_url(self, url: str):
        self.log.info(f"Cancelling {url}")
        if url in self._clients:
            # self._download_tasks[url].cancel()
            self._clients[url].close()

    async def drop_url(self, url: str):
        if url in self._clients:
            await self._clients[url].close_stream_of_url(url)
        await self.event_parser.drop_stream(url)

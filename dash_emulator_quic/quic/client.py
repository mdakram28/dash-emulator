import asyncio
import logging
from typing import List, Optional, cast, Tuple, Dict
from urllib.parse import urlparse

from aioquic.asyncio import connect
from aioquic.h3.connection import H3_ALPN
from aioquic.h3.events import HeadersReceived, DataReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.tls import SessionTicket
from dash_emulator.download import DownloadManager, DownloadEventListener

from dash_emulator_quic.quic.protocol import HttpProtocol


class QuicClientImpl(DownloadManager):
    log = logging.getLogger("QuicClientImpl")

    def __init__(self, event_listeners: List[DownloadEventListener], write_to_disk=False,
                 session_ticket: Optional[SessionTicket] = None):
        """
        Parameters
        ----------
        event_listeners: List[DownloadEventListener]
            A list of event listeners
        write_to_disk: bool
            If the file should be written to disks
        session_ticket : Optional[SessionTicket]
            The ticket containing the authentication information.
            With this ticket, The QUIC Client can have 0-RTT on the first request (if the server allows).
            The QUIC Client will use 0-RTT for the following requests no matter if this parameter is provided.
        """
        self.quic_configuration = QuicConfiguration(alpn_protocols=H3_ALPN, is_client=True)
        if session_ticket is not None:
            self.quic_configuration.session_ticket = session_ticket
        self.event_listeners = event_listeners
        self.write_to_disk = write_to_disk

        self._client: Optional[HttpProtocol] = None

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

    async def close(self):
        pass

    async def stop(self):
        pass

    def save_session_ticket(self, ticket: SessionTicket) -> None:
        """
        Callback which is invoked by the TLS engine when a new session ticket
        is received.
        """
        self.log.info("New session ticket received from server: " + ticket.server_name)
        self.quic_configuration.session_ticket = ticket

    async def start(self, host, port):
        async with connect(
                host,
                port,
                configuration=self.quic_configuration,
                create_protocol=HttpProtocol,
                session_ticket_handler=self.save_session_ticket,
                local_port=0,
                wait_connected=False,
        ) as client:
            self._client = client
            while True:
                await asyncio.sleep(10)

    @staticmethod
    def parse_headers(headers: List[Tuple[bytes, bytes]]) -> Dict[str, str]:
        result = dict()
        for header in headers:
            key, value = header
            result[key.decode('utf-8')] = value.decode('utf-8')
        return result

    async def download(self, url: str, save=False) -> Optional[bytes]:
        if self._client is None:
            # parse URL
            parsed = urlparse(url)
            host = parsed.hostname
            if parsed.port is not None:
                port = parsed.port
            else:
                port = 443
            asyncio.create_task(self.start(host, port))

        while self._client is None:
            await asyncio.sleep(0.5)

        for listener in self.event_listeners:
            await listener.on_transfer_start(url)

        client = cast(HttpProtocol, self._client)
        data = bytearray()
        headers = None
        # perform request
        async for event in client.get(url):
            if isinstance(event, HeadersReceived):
                headers = self.parse_headers(event.headers)
                self.log.info("Header received")
            else:
                event = cast(DataReceived, event)
                data.extend(event.data)
                for listener in self.event_listeners:
                    await listener.on_bytes_transferred(len(event.data), url, len(data),
                                                        int(headers.get('content-length')))
        for listener in self.event_listeners:
            await listener.on_transfer_end(len(data), url)
        return bytes(data) if save else None

    async def close_url(self, url):
        if self._client is not None:
            await self._client.close_stream_of_url(url)

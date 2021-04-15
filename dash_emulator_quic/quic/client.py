import asyncio
import logging
from typing import List, Optional, cast
from urllib.parse import urlparse

from aioquic.asyncio import connect
from aioquic.h3.connection import H3_ALPN
from aioquic.h3.events import HeadersReceived, DataReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.tls import SessionTicket
from dash_emulator.download import DownloadManager, DownloadEventListener

from dash_emulator_quic.quic.protocol import HttpClient


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

        self._client: Optional[HttpClient] = None

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
                create_protocol=HttpClient,
                session_ticket_handler=self.save_session_ticket,
                local_port=0,
                wait_connected=False,
        ) as client:
            self._client = client
            while True:
                await asyncio.sleep(10)

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

        client = cast(HttpClient, self._client)
        data = bytearray()
        # perform request
        async for event in client.get(url):
            if isinstance(event, HeadersReceived):
                # TODO: Parse header
                self.log.info("Header received")
            else:
                event = cast(DataReceived, event)
                data.extend(event.data)
                for listener in self.event_listeners:
                    await listener.on_bytes_transferred(len(event.data), url, len(data), len(event.data))
        for listener in self.event_listeners:
            await listener.on_transfer_end(len(data), url)
        return bytes(data) if save else None

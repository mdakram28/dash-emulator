import logging
import os
from os.path import join
from typing import Dict, Any, BinaryIO

from dash_emulator.download import DownloadEventListener
from dash_emulator.models import State
from dash_emulator.player import PlayerEventListener


class FileContentListener(DownloadEventListener, PlayerEventListener):
    files: dict[str, BinaryIO]
    log = logging.getLogger("FileContentListener")

    def __init__(self, run_dir: str = None):
        self.download_dir = join(run_dir, "downloaded")
        os.makedirs(self.download_dir, exist_ok=True)
        self.files = {}

    async def on_state_change(self, position: float, old_state: State, new_state: State):
        self.log.info(f"{new_state}")
        if new_state == State.END:
            for url, file in self.files.items():
                self.log.info(f"{url} : {file.tell()} bytes")
                file.close()
        pass

    async def on_position_change(self, position):
        pass

    async def on_buffer_level_change(self, buffer_level):
        pass

    async def on_bytes_transferred(self, length: int, url: str, position: int, size: int, content) -> None:
        if url not in self.files:
            self.files[url] = open(join(self.download_dir, url.split("/")[-1]), "wb")
        self.files[url].write(content)
        self.log.info(f"Saved {size} bytes")
        pass

    async def on_transfer_end(self, size: int, url: str) -> None:
        pass

    async def on_transfer_start(self, url) -> None:
        pass

    async def on_transfer_canceled(self, url: str, position: int, size: int) -> None:
        pass

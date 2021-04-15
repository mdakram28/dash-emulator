class BETAEvent:
    pass


class BandwidthUpdateEvent(BETAEvent):
    def __init__(self, bw: int):
        self.bw = bw


class BytesTransferredEvent(BETAEvent):
    def __init__(self, length: int, url: str, position: int, size: int):
        self.size = size
        self.position = position
        self.url = url
        self.length = length

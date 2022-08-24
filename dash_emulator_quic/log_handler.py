import logging
import sys
from datetime import datetime
from json import dumps
from logging import Handler
from pprint import pprint
import socket

class BetaLogHandler(Handler):

    def __init__(self, host, port, run_id):
        super().__init__()
        self.host = host
        self.port = port
        self._program_name = sys.argv[0]
        self._message_type = "beta-run-log"
        self.run_id = run_id
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.start_time = datetime.now().timestamp()

    def emit(self, record):
        message = {
            '@timestamp': self._format_timestamp(record.created),
            'level': record.levelname,
            'message': record.getMessage(),
            'program': self._program_name,
            'type': self._message_type,
            'run_id': self.run_id,
            'time_since_start': record.created - self.start_time,
            'logger': record.name,
        }
        sys.stdout.write(record.getMessage() + "\n")
        self.sock.sendto(bytes(dumps(message), "utf-8"), (self.host, self.port))

    def _format_timestamp(self, time_):
        timestamp = datetime.utcfromtimestamp(time_)
        formatted_timestamp = timestamp.strftime('%Y-%m-%dT%H:%M:%S')
        microsecond = int(timestamp.microsecond / 1000)
        return f'{formatted_timestamp}.{microsecond:03}Z'


def init_logging(run_id):
    handler = BetaLogHandler("logstash", 50000, run_id)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)20s %(levelname)8s:%(message)s',
                        handlers=[handler])

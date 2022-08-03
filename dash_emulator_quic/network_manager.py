import logging
import os
import subprocess
from threading import Thread
from time import sleep, time
from typing import List, Tuple

IF_NAME="eth0"
TARGET_IP="172.17.0.1"
NETEM_LIMIT=1000



class NetworkConfig:
    def __init__(self, bw, latency, drop, sustain, dump_events, log):
        self.bw = bw
        self.latency = latency
        self.drop = drop
        self.sustain = sustain
        self.dump_events = dump_events
        self.log = log

    def apply(self):

        cmd = [
            "docker", "exec", "--detach", os.environ["CONTAINER"],
            "bash", "-c",
            f"tc qdisc change dev {IF_NAME} handle 2: tbf rate {self.bw}kbit limit 1000 burst 3000 && " +
            f"tc qdisc change dev {IF_NAME} handle 3: netem limit {NETEM_LIMIT} delay {self.latency}ms 0ms loss {float(self.drop)*1:.3f}%"
        ]
        self.log.info(" ".join(cmd))

        t = round(time() * 1000)
        with open(self.dump_events, 'a') as f:
            f.write(f"#EVENT BW_SWITCH {t} {self.bw} {self.latency} {self.drop}")
        subprocess.check_call(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


class NetworkManager:
    log = logging.getLogger("NetworkManager")

    def __init__(self, bw_profile_path: str, dump_events):
        self.force_stop = False
        self.bw_profile_path = bw_profile_path
        self.delay = 1
        self.timeline: List[NetworkConfig] = []
        self.dump_events = dump_events

        with open(bw_profile_path) as f:
            last_line = ""
            for line in f:
                if line == last_line:
                    self.timeline[-1].sustain += self.delay
                    continue
                last_line = line
                [bw, latency, drop] = line.split(" ")
                self.timeline.append(NetworkConfig(bw, latency, drop, self.delay, dump_events, log=self.log))

    def start(self):
        for config in self.timeline:
            config.apply()
            self.log.info(f"Sustain Network Config for {config.sustain} seconds")
            for s in range(config.sustain):
                if self.force_stop:
                    return
                sleep(1)

    def start_bg(self):
        self.log.info("Starting Network Manager in background")
        t = Thread(target=self.start, daemon=True)
        t.start()

    def stop_bg(self):
        self.force_stop = True
        pass

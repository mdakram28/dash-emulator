from dataclasses import dataclass


@dataclass
class PlayerConfiguration(object):
    buffer_duration: float
    safe_buffer_level: float
    panic_buffer_level: float
    min_rebuffer_duration: float
    min_start_duration: float


def load_player_config(configuration) -> PlayerConfiguration:
    return PlayerConfiguration(**(configuration["player"]))
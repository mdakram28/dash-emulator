from dash_emulator_quic.abr import DashABRController
from dash_emulator_quic.bandwidth import BandwidthMeterImpl
from dash_emulator_quic.buffer import BufferManagerImpl
from dash_emulator_quic.config import Config
from dash_emulator_quic.download import DownloadManagerImpl
from dash_emulator_quic.event_logger import EventLogger
from dash_emulator_quic.mpd.parser import DefaultMPDParser
from dash_emulator_quic.mpd.providers import MPDProviderImpl
from dash_emulator_quic.player import DASHPlayer, Player
from dash_emulator_quic.quic.client import QuicClientImpl
from dash_emulator_quic.scheduler import SchedulerImpl


def build_dash_player() -> Player:
    cfg = Config
    buffer_manager = BufferManagerImpl()
    event_logger = EventLogger()
    mpd_provider = MPDProviderImpl(DefaultMPDParser(), cfg.update_interval, DownloadManagerImpl([]))
    bandwidth_meter = BandwidthMeterImpl(cfg.max_initial_bitrate, cfg.smoothing_factor, [])
    download_manager = DownloadManagerImpl([bandwidth_meter])
    abr_controller = DashABRController(2, 4, bandwidth_meter, buffer_manager)
    scheduler = SchedulerImpl(5, cfg.update_interval, download_manager, bandwidth_meter, buffer_manager,
                              abr_controller, [event_logger])
    return DASHPlayer(cfg.update_interval, min_rebuffer_duration=1, min_start_buffer_duration=2,
                      buffer_manager=buffer_manager, mpd_provider=mpd_provider, scheduler=scheduler,
                      listeners=[event_logger])


def build_dash_player_over_quic() -> Player:
    cfg = Config
    buffer_manager = BufferManagerImpl()
    event_logger = EventLogger()
    mpd_provider = MPDProviderImpl(DefaultMPDParser(), cfg.update_interval, QuicClientImpl([]))
    bandwidth_meter = BandwidthMeterImpl(cfg.max_initial_bitrate, cfg.smoothing_factor, [])
    download_manager = QuicClientImpl([bandwidth_meter])
    abr_controller = DashABRController(2, 4, bandwidth_meter, buffer_manager)
    scheduler = SchedulerImpl(5, cfg.update_interval, download_manager, bandwidth_meter, buffer_manager,
                              abr_controller, [event_logger])
    return DASHPlayer(cfg.update_interval, min_rebuffer_duration=1, min_start_buffer_duration=2,
                      buffer_manager=buffer_manager, mpd_provider=mpd_provider, scheduler=scheduler,
                      listeners=[event_logger])

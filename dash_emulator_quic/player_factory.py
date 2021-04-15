from dash_emulator.abr import DashABRController
from dash_emulator.bandwidth import BandwidthMeterImpl
from dash_emulator.buffer import BufferManager, BufferManagerImpl
from dash_emulator.config import Config
from dash_emulator.event_logger import EventLogger
from dash_emulator.mpd import MPDProvider
from dash_emulator.mpd.parser import DefaultMPDParser
from dash_emulator.mpd.providers import MPDProviderImpl
from dash_emulator.player import DASHPlayer
from dash_emulator.scheduler import SchedulerImpl, Scheduler

from dash_emulator_quic.beta.beta import BETAManagerImpl
from dash_emulator_quic.quic.client import QuicClientImpl


def build_dash_player_over_quic(beta=False):
    """
    Build a MPEG-DASH Player over QUIC network

    Returns
    -------
    player: Player
        A MPEG-DASH Player
    """
    if not beta:
        cfg = Config
        buffer_manager: BufferManager = BufferManagerImpl()
        event_logger = EventLogger()
        mpd_provider: MPDProvider = MPDProviderImpl(DefaultMPDParser(), cfg.update_interval, QuicClientImpl([]))
        bandwidth_meter = BandwidthMeterImpl(cfg.max_initial_bitrate, cfg.smoothing_factor, [])
        download_manager = QuicClientImpl([bandwidth_meter])
        abr_controller = DashABRController(2, 4, bandwidth_meter, buffer_manager)
        scheduler: Scheduler = SchedulerImpl(5, cfg.update_interval, download_manager, bandwidth_meter, buffer_manager,
                                             abr_controller, [event_logger])
        return DASHPlayer(cfg.update_interval, min_rebuffer_duration=1, min_start_buffer_duration=2,
                          buffer_manager=buffer_manager, mpd_provider=mpd_provider, scheduler=scheduler,
                          listeners=[event_logger])
    else:
        cfg = Config
        buffer_manager: BufferManager = BufferManagerImpl()
        event_logger = EventLogger()
        mpd_provider: MPDProvider = MPDProviderImpl(DefaultMPDParser(), cfg.update_interval, QuicClientImpl([]))
        bandwidth_meter = BandwidthMeterImpl(cfg.max_initial_bitrate, cfg.smoothing_factor, [])
        download_manager = QuicClientImpl([bandwidth_meter])

        beta_manager = BETAManagerImpl(mpd_provider, download_manager)
        download_manager.add_listener(beta_manager)
        bandwidth_meter.add_listener(beta_manager)

        abr_controller = DashABRController(2, 4, bandwidth_meter, buffer_manager)
        scheduler: Scheduler = SchedulerImpl(5, cfg.update_interval, download_manager, bandwidth_meter, buffer_manager,
                                             abr_controller, [event_logger, beta_manager])
        return DASHPlayer(cfg.update_interval, min_rebuffer_duration=1, min_start_buffer_duration=2,
                          buffer_manager=buffer_manager, mpd_provider=mpd_provider, scheduler=scheduler,
                          listeners=[event_logger, beta_manager], services=[beta_manager])

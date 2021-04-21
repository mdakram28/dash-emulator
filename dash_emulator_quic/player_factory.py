from dash_emulator.abr import DashABRController
from dash_emulator.bandwidth import BandwidthMeterImpl
from dash_emulator.buffer import BufferManager, BufferManagerImpl
from dash_emulator.config import Config
from dash_emulator.event_logger import EventLogger
from dash_emulator.mpd import MPDProvider
from dash_emulator.mpd.parser import DefaultMPDParser
from dash_emulator.player import DASHPlayer
from dash_emulator.scheduler import SchedulerImpl, Scheduler

from dash_emulator_quic.beta.beta import BETAManagerImpl
from dash_emulator_quic.beta.vq_threshold import MockVQThresholdManager
from dash_emulator_quic.mpd.providers import BETAMPDProviderImpl
from dash_emulator_quic.quic.client import QuicClientImpl
from dash_emulator_quic.quic.event_parser import H3EventParserImpl
from dash_emulator_quic.scheduler.scheduler import BETAScheduler, BETASchedulerImpl


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
        mpd_provider: MPDProvider = BETAMPDProviderImpl(DefaultMPDParser(), cfg.update_interval,
                                                        QuicClientImpl([], event_parser=H3EventParserImpl()))
        bandwidth_meter = BandwidthMeterImpl(cfg.max_initial_bitrate, cfg.smoothing_factor, [])
        h3_event_parser = H3EventParserImpl(listeners=[bandwidth_meter])
        download_manager = QuicClientImpl([bandwidth_meter], event_parser=h3_event_parser)
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
        mpd_provider: MPDProvider = BETAMPDProviderImpl(DefaultMPDParser(), cfg.update_interval,
                                                        QuicClientImpl([], H3EventParserImpl()))
        bandwidth_meter = BandwidthMeterImpl(cfg.max_initial_bitrate, cfg.smoothing_factor, [])
        h3_event_parser = H3EventParserImpl([bandwidth_meter])
        download_manager = QuicClientImpl([bandwidth_meter], h3_event_parser)

        vq_threshold_manager = MockVQThresholdManager()
        beta_manager = BETAManagerImpl(mpd_provider, download_manager, vq_threshold_manager, panic_buffer_level=2.5)
        download_manager.add_listener(beta_manager)
        bandwidth_meter.add_listener(beta_manager)
        h3_event_parser.add_listener(beta_manager)

        abr_controller = DashABRController(2, 4, bandwidth_meter, buffer_manager)
        scheduler: BETAScheduler = BETASchedulerImpl(5, cfg.update_interval, download_manager, bandwidth_meter,
                                                     buffer_manager,
                                                     abr_controller, [event_logger, beta_manager])
        return DASHPlayer(cfg.update_interval, min_rebuffer_duration=1, min_start_buffer_duration=2,
                          buffer_manager=buffer_manager, mpd_provider=mpd_provider, scheduler=scheduler,
                          listeners=[event_logger, beta_manager], services=[beta_manager])

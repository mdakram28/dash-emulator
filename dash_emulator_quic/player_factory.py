import os
from os.path import join
from typing import Tuple
import os.path as path

from exp_common.exp_recorder import ExpWriterJson

from dash_emulator_quic.analyzers.file_content_listener import FileContentListener

from dash_emulator.abr import DashABRController
from dash_emulator.bandwidth import BandwidthMeterImpl
from dash_emulator.buffer import BufferManager, BufferManagerImpl
from dash_emulator.config import Config
from dash_emulator.event_logger import EventLogger
from dash_emulator.mpd import MPDProvider
from dash_emulator.mpd.parser import DefaultMPDParser
from dash_emulator.player import DASHPlayer
from dash_emulator.scheduler import Scheduler

from dash_emulator_quic.abr import ExtendedABRController, BetaABRController
from dash_emulator_quic.analyzers.analyer import BETAPlaybackAnalyzer, BETAPlaybackAnalyzerConfig, PlaybackAnalyzer
from dash_emulator_quic.beta.beta import BETAManagerImpl
from dash_emulator_quic.beta.vq_threshold import MockVQThresholdManager
from dash_emulator_quic.config import PlayerConfiguration, DownloaderConfiguration, DownloaderProtocolEnum
from dash_emulator_quic.downloader.tcp import TCPClientImpl
from dash_emulator_quic.mpd.providers import BETAMPDProviderImpl
from dash_emulator_quic.downloader.quic.client import QuicClientImpl
from dash_emulator_quic.downloader.quic.event_parser import H3EventParserImpl
from dash_emulator_quic.scheduler.scheduler import BETAScheduler, BETASchedulerImpl
import sslkeylog

def build_dash_player_over_quic(player_configuration: PlayerConfiguration,
                                downloader_configuration: DownloaderConfiguration,
                                beta=False, plot_output=None,
                                event_logs=None, run_dir=None) -> Tuple[DASHPlayer, PlaybackAnalyzer]:
    """
    Build a MPEG-DASH Player over QUIC network

    Returns
    -------
    player: Player
        A MPEG-DASH Player
    """
    BUFFER_DURATION = player_configuration.player_buffer_settings.buffer_duration
    SAFE_BUFFER_LEVEL = player_configuration.player_buffer_settings.safe_buffer_level
    PANIC_BUFFER_LEVEL = player_configuration.player_buffer_settings.panic_buffer_level
    MIN_REBUFFER_DURATION = player_configuration.player_buffer_settings.min_rebuffer_duration
    MIN_START_DURATION = player_configuration.player_buffer_settings.min_start_duration

    print("**************************", downloader_configuration.protocol)
    if os.getenv('SSLKEYLOGFILE') is not None:
        sslkeylog.set_keylog(os.getenv('SSLKEYLOGFILE'))

    cont_bw_window = 1
    max_packet_delay = 2
    file_content_listener = FileContentListener(run_dir=run_dir)
    if not beta:
        cfg = Config
        buffer_manager: BufferManager = BufferManagerImpl()

        if downloader_configuration.protocol is DownloaderProtocolEnum.QUIC:
            mpd_provider: MPDProvider = BETAMPDProviderImpl(DefaultMPDParser(), cfg.update_interval,
                                                            QuicClientImpl([], event_parser=H3EventParserImpl(listeners=[file_content_listener])))
        else:
            mpd_provider: MPDProvider = BETAMPDProviderImpl(DefaultMPDParser(), cfg.update_interval, TCPClientImpl([file_content_listener]))
        event_logger = EventLogger(mpd_provider, recorder=event_logs)

        analyzer: BETAPlaybackAnalyzer = BETAPlaybackAnalyzer(
            BETAPlaybackAnalyzerConfig(save_plots_dir=plot_output, run_dir=run_dir, recorder=event_logs),
            mpd_provider
        )
        bandwidth_meter = BandwidthMeterImpl(cfg.max_initial_bitrate, cfg.smoothing_factor, [analyzer], cont_bw_window=cont_bw_window,
            max_packet_delay=max_packet_delay)
        h3_event_parser = H3EventParserImpl(listeners=[bandwidth_meter, analyzer])
        if downloader_configuration.protocol is DownloaderProtocolEnum.QUIC:
            download_manager = QuicClientImpl([bandwidth_meter, analyzer], event_parser=h3_event_parser)
        else:
            download_manager = TCPClientImpl([bandwidth_meter, analyzer, file_content_listener])
        abr_controller = BetaABRController(
            DashABRController(PANIC_BUFFER_LEVEL, SAFE_BUFFER_LEVEL, bandwidth_meter, buffer_manager, mpd_provider))
        scheduler: Scheduler = BETASchedulerImpl(BUFFER_DURATION, cfg.update_interval, download_manager,
                                                 bandwidth_meter,
                                                 buffer_manager, abr_controller, [event_logger, analyzer])
        return DASHPlayer(cfg.update_interval, min_rebuffer_duration=MIN_REBUFFER_DURATION,
                          min_start_buffer_duration=MIN_START_DURATION,
                          buffer_manager=buffer_manager, mpd_provider=mpd_provider, scheduler=scheduler,
                          listeners=[event_logger, analyzer, file_content_listener]), analyzer
    else:
        cfg = Config
        buffer_manager: BufferManager = BufferManagerImpl()
        if downloader_configuration.protocol is DownloaderProtocolEnum.QUIC:
            mpd_provider: MPDProvider = BETAMPDProviderImpl(DefaultMPDParser(), cfg.update_interval,
                                                            QuicClientImpl([file_content_listener], H3EventParserImpl(listeners=[file_content_listener])))
        else:
            mpd_provider: MPDProvider = BETAMPDProviderImpl(DefaultMPDParser(), cfg.update_interval, TCPClientImpl([file_content_listener]))
        event_logger = EventLogger(mpd_provider, recorder=event_logs)

        analyzer: BETAPlaybackAnalyzer = BETAPlaybackAnalyzer(
            BETAPlaybackAnalyzerConfig(save_plots_dir=plot_output, run_dir=run_dir, recorder=event_logs),
            mpd_provider)
        bandwidth_meter = BandwidthMeterImpl(cfg.max_initial_bitrate, cfg.smoothing_factor, [analyzer], cont_bw_window=cont_bw_window, max_packet_delay=max_packet_delay)
        h3_event_parser = H3EventParserImpl([bandwidth_meter, analyzer, file_content_listener])
        if downloader_configuration.protocol is DownloaderProtocolEnum.QUIC:
            download_manager = QuicClientImpl([bandwidth_meter, analyzer], h3_event_parser)
        else:
            download_manager = TCPClientImpl([bandwidth_meter, analyzer, file_content_listener])

        vq_threshold_manager = MockVQThresholdManager()
        beta_manager = BETAManagerImpl(mpd_provider, download_manager, vq_threshold_manager, panic_buffer_level=PANIC_BUFFER_LEVEL, safe_buffer_level=SAFE_BUFFER_LEVEL)
        download_manager.add_listener(beta_manager)
        bandwidth_meter.add_listener(beta_manager)
        h3_event_parser.add_listener(beta_manager)

        abr_controller: ExtendedABRController = BetaABRController(
            DashABRController(PANIC_BUFFER_LEVEL, SAFE_BUFFER_LEVEL, bandwidth_meter, buffer_manager, mpd_provider)
        )

        scheduler: BETAScheduler = BETASchedulerImpl(BUFFER_DURATION, cfg.update_interval, download_manager,
                                                     bandwidth_meter,
                                                     buffer_manager, abr_controller,
                                                     [event_logger, beta_manager, analyzer])
        return DASHPlayer(cfg.update_interval, min_rebuffer_duration=MIN_REBUFFER_DURATION,
                          min_start_buffer_duration=MIN_START_DURATION,
                          buffer_manager=buffer_manager, mpd_provider=mpd_provider, scheduler=scheduler,
                          listeners=[event_logger, beta_manager, analyzer, file_content_listener], services=[beta_manager]), analyzer

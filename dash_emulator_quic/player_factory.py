from typing import Tuple
import os.path as path
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
                                dump_results=None, dump_events=None,
                                run_id=None,
                                ssl_keylog_file=None) -> Tuple[DASHPlayer, PlaybackAnalyzer]:
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
    if ssl_keylog_file is not None:
        sslkeylog.set_keylog(ssl_keylog_file)

    local_dump_events = path.join(path.dirname(dump_results),"event_logs.txt")
    if not beta:
        cfg = Config
        buffer_manager: BufferManager = BufferManagerImpl()

        if downloader_configuration.protocol is DownloaderProtocolEnum.QUIC:
            mpd_provider: MPDProvider = BETAMPDProviderImpl(DefaultMPDParser(), cfg.update_interval,
                                                            QuicClientImpl([], event_parser=H3EventParserImpl(), ssl_keylog_file=ssl_keylog_file))
            cont_bw_window = 0.2
            max_packet_delay = 1
        else:
            mpd_provider: MPDProvider = BETAMPDProviderImpl(DefaultMPDParser(), cfg.update_interval, TCPClientImpl([], ssl_keylog_file=ssl_keylog_file))
            cont_bw_window = 1.0
            max_packet_delay = 10
        event_logger = EventLogger(dump_events, run_id, mpd_provider)

        analyzer: BETAPlaybackAnalyzer = BETAPlaybackAnalyzer(
            BETAPlaybackAnalyzerConfig(save_plots_dir=plot_output, dump_results_path=dump_results, dump_events=local_dump_events, run_id=run_id),
            mpd_provider
        )
        bandwidth_meter = BandwidthMeterImpl(cfg.max_initial_bitrate, cfg.smoothing_factor, [analyzer], cont_bw_window=cont_bw_window, 
            max_packet_delay=max_packet_delay)
        h3_event_parser = H3EventParserImpl(listeners=[bandwidth_meter, analyzer])
        if downloader_configuration.protocol is DownloaderProtocolEnum.QUIC:
            download_manager = QuicClientImpl([bandwidth_meter, analyzer], event_parser=h3_event_parser, ssl_keylog_file=ssl_keylog_file)
        else:
            download_manager = TCPClientImpl([bandwidth_meter, analyzer], ssl_keylog_file=ssl_keylog_file)
        abr_controller = BetaABRController(
            DashABRController(PANIC_BUFFER_LEVEL, SAFE_BUFFER_LEVEL, bandwidth_meter, buffer_manager, mpd_provider))
        scheduler: Scheduler = BETASchedulerImpl(BUFFER_DURATION, cfg.update_interval, download_manager,
                                                 bandwidth_meter,
                                                 buffer_manager, abr_controller, [event_logger, analyzer])
        return DASHPlayer(cfg.update_interval, min_rebuffer_duration=MIN_REBUFFER_DURATION,
                          min_start_buffer_duration=MIN_START_DURATION,
                          buffer_manager=buffer_manager, mpd_provider=mpd_provider, scheduler=scheduler,
                          listeners=[event_logger, analyzer]), analyzer
    else:
        cfg = Config
        buffer_manager: BufferManager = BufferManagerImpl()
        if downloader_configuration.protocol is DownloaderProtocolEnum.QUIC:
            mpd_provider: MPDProvider = BETAMPDProviderImpl(DefaultMPDParser(), cfg.update_interval,
                                                            QuicClientImpl([], H3EventParserImpl(), ssl_keylog_file=ssl_keylog_file))
            cont_bw_window = 0.2
            max_packet_delay = 1
        else:
            mpd_provider: MPDProvider = BETAMPDProviderImpl(DefaultMPDParser(), cfg.update_interval, TCPClientImpl([], ssl_keylog_file=ssl_keylog_file))
            cont_bw_window = 1.0
            max_packet_delay = 10
        event_logger = EventLogger(dump_events, run_id, mpd_provider)

        analyzer: BETAPlaybackAnalyzer = BETAPlaybackAnalyzer(
            BETAPlaybackAnalyzerConfig(save_plots_dir=plot_output, dump_results_path=dump_results, dump_events=local_dump_events, run_id=run_id),
            mpd_provider)
        bandwidth_meter = BandwidthMeterImpl(cfg.max_initial_bitrate, cfg.smoothing_factor, [analyzer], cont_bw_window=cont_bw_window, max_packet_delay=max_packet_delay)
        h3_event_parser = H3EventParserImpl([bandwidth_meter, analyzer])
        if downloader_configuration.protocol is DownloaderProtocolEnum.QUIC:
            download_manager = QuicClientImpl([bandwidth_meter, analyzer], h3_event_parser, ssl_keylog_file=ssl_keylog_file)
        else:
            download_manager = TCPClientImpl([bandwidth_meter, analyzer], ssl_keylog_file=ssl_keylog_file)

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
                          listeners=[event_logger, beta_manager, analyzer], services=[beta_manager]), analyzer

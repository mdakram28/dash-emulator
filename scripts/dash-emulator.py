#!/usr/bin/env python3

import argparse
import asyncio
import logging
import pathlib
import re
import sys
from typing import Dict, Union

import uvloop

from dash_emulator_quic.config import load_config_env
from dash_emulator_quic.player_factory import build_dash_player_over_quic
from dash_emulator_quic.network_manager import NetworkManager

log = logging.getLogger(__name__)

PLAYER_TARGET = "target"


def create_parser():
    arg_parser = argparse.ArgumentParser(description="Accept for the emulator")
    # Add here

    arg_parser.add_argument("--beta", action="store_true", help="Enable BETA")
    arg_parser.add_argument("--proxy", type=str, help='NOT IMPLEMENTED YET')
    arg_parser.add_argument("--plot", required=False, default=None, type=str, help="The folder to save plots")
    arg_parser.add_argument("--dump-results", required=False, default=None, type=str, help="Dump the results")
    arg_parser.add_argument("--dump-events-result", required=False, default=None, type=str, help="Dump the events for teh result")
    arg_parser.add_argument("--dump-events-run", required=False, default=None, type=str, help="Dump the events for the run")
    arg_parser.add_argument("--run-id", required=False, default=None, type=str, help="Run ID")
    arg_parser.add_argument("--ssl-keylog-file", required=False, default=None, type=str, help="SSL Keylog master file")
    arg_parser.add_argument("--bw-profile", required=False, default=None, type=str, help="Bandwidth profile file path")
    arg_parser.add_argument("--env", required=False, default=None, type=str, help="Environment to use")
    arg_parser.add_argument("-y", required=False, default=False, action='store_true',
                            help="Automatically overwrite output folder")
    arg_parser.add_argument(PLAYER_TARGET, type=str, help="Target MPD file link")
    return arg_parser


def validate_args(arguments: Dict[str, Union[int, str, None]]) -> bool:
    # Validate target
    # args.PLAYER_TARGET is required
    if "target" not in arguments:
        log.error("Argument \"%s\" is required" % PLAYER_TARGET)
        return False
    # HTTP or HTTPS protocol
    results = re.match("^(http|https)://", arguments[PLAYER_TARGET])
    if results is None:
        log.error("Argument \"%s\" (%s) is not in the right format" % (
            PLAYER_TARGET, arguments[PLAYER_TARGET]))
        return False

    # Validate proxy
    # TODO

    # Validate Output
    if arguments["plot"] is not None:
        path = pathlib.Path(arguments['plot'])
        path.mkdir(parents=True, exist_ok=True)

    return True


if __name__ == '__main__':
    try:
        assert sys.version_info.major >= 3 and sys.version_info.minor >= 3
    except AssertionError:
        print("Python 3.3+ is required.")
        exit(-1)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)20s %(levelname)8s:%(message)s')
    parser = create_parser()
    args = parser.parse_args()

    args = vars(args)

    validated = validate_args(args)

    if not validated:
        log.error("Arguments validation error, exit.")
        exit(-1)

    (player_config, downloader_config) = load_config_env(args['env'])

    uvloop.install()


    async def main():
        player, analyzer = build_dash_player_over_quic(
            player_config,
            downloader_config,
            beta=args["beta"],
            plot_output=args["plot"],
            dump_results=args['dump_results'],
            dump_events=args['dump_events_result'],
            run_id=args["run_id"],
            ssl_keylog_file=args["ssl_keylog_file"])

        # player = build_dash_player()
        network_manager = NetworkManager(bw_profile_path=args['bw_profile'], dump_events=args['dump_events_run'])
        network_manager.start_bg()

        await player.start(args["target"])
        analyzer.save(sys.stdout)

        network_manager.stop_bg()
        # await asyncio.sleep(1000000)


    asyncio.run(main())

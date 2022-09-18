#!/usr/bin/env python3

import argparse
import asyncio
import json
import logging
import pathlib
import re
import sys
from os.path import join
from typing import Dict, Union

<<<<<<< HEAD
import uvloop
from exp_common.exp_recorder import ExpWriterJson

from dash_emulator_quic.config import load_config_env
from dash_emulator_quic.log_handler import init_logging
from dash_emulator_quic.network_manager import NetworkManager
from dash_emulator_quic.player_factory import build_dash_player_over_quic
=======
from dash_emulator.player_factory import build_dash_player
>>>>>>> temp

log = logging.getLogger(__name__)

PLAYER_TARGET = "target"


def create_parser():
    arg_parser = argparse.ArgumentParser(description="Accept for the emulator")
    # Add here

    arg_parser.add_argument("--beta", action="store_true", help="Enable BETA")
    arg_parser.add_argument("--proxy", type=str, help='NOT IMPLEMENTED YET')
    arg_parser.add_argument("--plot", required=False, default=None, type=str, help="The folder to save plots")
    arg_parser.add_argument("--env", required=False, default=None, type=str, help="Environment to use")
    arg_parser.add_argument("--run-id", required=False, type=str, help="Run ID")
    arg_parser.add_argument("--run-dir", required=False, type=str, help="Run Directory")
    arg_parser.add_argument("--bw-profile", required=False, default=None, type=str, help="Bandwidth profile file path")
    arg_parser.add_argument("--config-file", required=False, default=None, type=str, help="Load config from file")
    arg_parser.add_argument("-y", required=False, default=False, action='store_true',
                            help="Automatically overwrite output folder")
    arg_parser.add_argument(PLAYER_TARGET, type=str, help="Target MPD file link")
    return arg_parser


def validate_args(arguments: Dict[str, Union[int, str, None]]) -> bool:
    # Validate target
    # args.PLAYER_TARGET is required
<<<<<<< HEAD
    if "target" not in arguments and arguments.get("config_file") is None:
=======
    if "target" not in arguments:
>>>>>>> temp
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
<<<<<<< HEAD
    if arguments["plot"] is not None:
        path = pathlib.Path(arguments['plot'])
=======
    if arguments["output"] is not None:
        path = pathlib.Path(arguments['output'])
>>>>>>> temp
        path.mkdir(parents=True, exist_ok=True)

    return True


if __name__ == '__main__':
    try:
        assert sys.version_info.major >= 3 and sys.version_info.minor >= 3
    except AssertionError:
        print("Python 3.3+ is required.")
        exit(-1)

    parser = create_parser()
    args = parser.parse_args()

    args = vars(args)

    if args["config_file"] is not None:
        with open(args['config_file']) as f:
            config = json.load(f)
        args["run_id"] = args["run_id"] or config["runId"]
        args["run_dir"] = args["run_dir"] or config["runDir"]
        args["bw_profile"] = args["bw_profile"] or config["bwProfile"]
        args["beta"] = config["beta"]
        args["target"] = args["target"] or config["target"]
        args["env"] = args["env"] or config["env"]

    validated = validate_args(args)

    if not validated:
        log.error("Arguments validation error, exit.")
        exit(-1)

<<<<<<< HEAD
    init_logging(run_id=args["run_id"])
=======
    logging.basicConfig(level=logging.INFO)

    player = build_dash_player()
>>>>>>> temp

    (player_config, downloader_config) = load_config_env(args['env'])

    uvloop.install()


    async def main():
        event_logs = ExpWriterJson(join(args['run_dir'], "event_logs.txt"))
        player, analyzer = build_dash_player_over_quic(
            player_config,
            downloader_config,
            beta=args["beta"],
            plot_output=args["plot"],
            event_logs=event_logs,
            run_dir=args["run_dir"])

        # player = build_dash_player()
        network_manager = NetworkManager(bw_profile_path=args['bw_profile'], recorder=event_logs)
        network_manager.start_bg()

        await player.start(args["target"])
        analyzer.save(sys.stdout)

        network_manager.stop_bg()
        # await asyncio.sleep(1000000)


    asyncio.run(main())

#!/usr/bin/env python3

import argparse
import json
import math
import pathlib
import re
import sys
from glob import glob
from typing import Dict, List

import numpy as np


def main():
    parser = argparse.ArgumentParser("Parse the playback reports generated by dash-emulator-quic")
    parser.add_argument("--folder", required=True, type=str, help="Folder containing all reports")
    parser.add_argument("--average-stall-dur", action="store_true", help="Print average stall durations")
    parser.add_argument("--average-stall-num", action="store_true", help="Print average stall numbers")
    parser.add_argument("--average-quality-switch-num", action="store_true",
                        help="Print the average number of quality switches")
    parser.add_argument("--std-stall-dur", action="store_true", help="Print the standard deviation of stall durations")
    parser.add_argument("--std-stall-num", action="store_true", help="Print the standard deviation of stall numbers")
    parser.add_argument("--std-quality-switch-num", action="store_true",
                        help="Print the standard deviation of number of quality switches")
    parser.add_argument("--vmaf", action="store_true", help="Enable VMAF analysis")
    parser.add_argument("--dataset-home", type=str, default=None, help="Path to the dataset folder")
    args = parser.parse_args()

    if args.vmaf and args.dataset_home is None:
        print("--dataset-home is required if vmaf is enabled")
        exit(0)

    classified_reports = fetch_reports_from_folder(args.folder)
    print_header(args.average_stall_dur, args.average_stall_num, args.average_quality_switch_num, args.std_stall_dur,
                 args.std_stall_num, args.std_quality_switch_num, args.vmaf)
    for video in sorted(classified_reports.keys()):
        files = classified_reports[video]
        PlaybackReportAnalyzer(video, files, args.dataset_home).analyze(args.average_stall_dur, args.average_stall_num,
                                                                        args.average_quality_switch_num,
                                                                        args.std_stall_dur,
                                                                        args.std_stall_num, args.std_quality_switch_num,
                                                                        args.vmaf)


def print_header(average_stall_dur, average_stall_num, average_quality_switch_num, std_stall_dur, std_stall_num,
                 std_quality_switch_num, vmaf):
    sys.stdout.write("%-20s" % "Video")
    if average_stall_dur:
        sys.stdout.write("%-20s" % "avg-stall-dur")
    if std_stall_dur:
        sys.stdout.write("%-20s" % "std-stall-dur")
    if average_stall_num:
        sys.stdout.write("%-20s" % "avg-stall-num")
    if std_stall_num:
        sys.stdout.write("%-20s" % "std-stall-num")
    if average_quality_switch_num:
        sys.stdout.write("%-20s" % "avg-quality-switch")
    if std_quality_switch_num:
        sys.stdout.write("%-20s" % "std-quality-switch")
    if vmaf:
        sys.stdout.write("%-20s" % "avg-vmaf")
        sys.stdout.write("%-20s" % "std-vmaf")
    sys.stdout.write("\n")


def fetch_reports_from_folder(folder: str) -> Dict[str, List[str]]:
    files = glob(f"{folder}/*.json")
    classified_files = {}
    for file_path in files:
        filename = pathlib.Path(file_path).stem
        video, index = filename.rsplit('-', maxsplit=1)
        if video not in classified_files:
            classified_files[video] = []
        classified_files[video].append(file_path)
    return classified_files


class PlaybackReportAnalyzer:
    def __init__(self, video: str, reports: List[str], dataset_home=None):
        self.video = video
        self.reports = reports
        self._reports_data = None
        self._dataset_home = dataset_home
        self._vmaf_vals = None

    def analyze(
            self,
            average_stall_dur=False,
            average_stall_num=False,
            average_quality_switch_num=False,
            std_stall_dur=False,
            std_stall_num=False,
            std_quality_switch_num=False,
            vmaf=False
    ):
        self._reports_data = []
        for report in self.reports:
            with open(report) as f:
                self._reports_data.append(json.load(f))
        sys.stdout.write("%-20s" % self.video)

        avg_stall_dur_value, std_stall_dur_value = self._calculate_stall_dur()
        avg_stall_num_value, std_stall_num_value = self._calculate_stall_num()
        avg_switch_num_value, std_switch_num_value = self._calculate_quality_switch_num()

        if average_stall_dur:
            sys.stdout.write("%-20.2f" % avg_stall_dur_value)
        if std_stall_dur:
            sys.stdout.write("%-20.2f" % std_stall_dur_value)
        if average_stall_num:
            sys.stdout.write("%-20.2f" % avg_stall_num_value)
        if std_stall_num:
            sys.stdout.write("%-20.2f" % std_stall_num_value)
        if average_quality_switch_num:
            sys.stdout.write("%-20.2f" % avg_switch_num_value)
        if std_quality_switch_num:
            sys.stdout.write("%-20.2f" % std_switch_num_value)
        if vmaf:
            avg_vmaf, std_vmaf_value = self._calculate_vmaf()
            sys.stdout.write("%-20.2f" % avg_vmaf)
            sys.stdout.write("%-20.2f" % std_vmaf_value)
        sys.stdout.write("\n")

    def _calculate_stall_dur(self):
        stall_durs = [data["dur_stall"] for data in self._reports_data]
        return np.average(stall_durs), np.std(stall_durs)

    def _calculate_stall_num(self):
        stall_nums = [data["num_stall"] for data in self._reports_data]
        return np.average(stall_nums), np.std(stall_nums)

    def _calculate_quality_switch_num(self):
        quality_switch_nums = [data["num_quality_switches"] for data in self._reports_data]
        return np.average(quality_switch_nums), np.std(quality_switch_nums)

    def _load_vmaf(self):
        assert self._dataset_home is not None
        vmaf = dict()  # vmaf[quality index][drop_rate][segment_index]
        video_name = self.video.split('-')[0]
        composed_vmaf_reports = glob(f"{self._dataset_home}/av1/{video_name}/*-composed.txt")
        pattern = re.compile(r"[\s\S]+quality(\d)-drop(\d+)-composed\.txt")
        for composed_vmaf_report in composed_vmaf_reports:
            matches = re.match(pattern, composed_vmaf_report)
            assert matches is not None
            quality_index = int(matches.group(1)) - 1
            drop_rate = int(matches.group(2))
            if quality_index not in vmaf:
                vmaf[quality_index] = dict()
            with open(composed_vmaf_report) as f:
                vals = [float(line.strip()) for line in f.readlines()]
                vmaf[quality_index][drop_rate] = vals
        self._vmaf_vals = vmaf

    def _calculate_vmaf(self):
        self._load_vmaf()
        vmaf_of_videos = []
        for report in self._reports_data:
            segments = report["segments"]
            vmaf_vals = []
            for segment in segments:
                segment_index = segment['index']
                quality_index = segment['quality']
                ratio = segment['ratio']
                drop_rate = math.ceil((1.0 - ratio) * 5) * 20
                vmaf_val = self._vmaf_vals[quality_index][drop_rate][segment_index]
                vmaf_vals.append(vmaf_val)
            vmaf_of_videos.append(sum(vmaf_vals) / len(vmaf_vals))
        return np.average(vmaf_of_videos), np.std(vmaf_of_videos)



if __name__ == '__main__':
    main()

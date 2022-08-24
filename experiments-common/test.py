import os.path
import time

from exp_common.exp_events import TYPE_MAPPING_CLASS, TYPE_MAPPING_KEYS, ExpEvent_PlaybackStart
from exp_common.exp_recorder import ExpWriterJson, ExpWriterText, ExpReader


def run_test():
    print(TYPE_MAPPING_CLASS)
    print(TYPE_MAPPING_KEYS)

    log_file_json = "test_logs_json.txt"
    log_file_text = "test_logs_text.txt"
    files = [log_file_json, log_file_text]

    for f in files:
        if os.path.exists(f):
            os.unlink(f)

    writer = ExpWriterJson(log_file_json)
    writer.write_event(ExpEvent_PlaybackStart(int(time.time()*1000)))
    writer = ExpWriterText(log_file_text)
    writer.write_event(ExpEvent_PlaybackStart(int(time.time()*1000)))

    print()
    reader = ExpReader(log_file_json)
    for event in reader.read_events():
        print(event.__dict__)
    reader = ExpReader(log_file_text)
    for event in reader.read_events():
        print(event.__dict__)

    print()
    print()
    for f_name in files:
        print()
        print(f"--content_start ({f_name})--")
        with open(f_name) as f:
            print(f.read())
        print("--content_end--")
        os.unlink(f_name)


if __name__ == "__main__":
    run_test()

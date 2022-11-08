import os
from time import sleep
from datetime import datetime, timedelta

from settings import LEXPATH


def wait(duration):  # pass-through for testing
    sleep(duration)


class ServiceRequestDoorkeeper:
    """A self-made shared state for multiprocessing and single threaded"""

    def __init__(self, file_path, niceness):
        self.file_path = file_path
        self.niceness = niceness

    def get(self) -> datetime:
        try:
            with open(self.file_path, mode="r") as f:
                result = datetime.fromtimestamp(float(f.read()))
        except FileNotFoundError:
            result = datetime.now()
            self.set(result)
        return result

    def set(self, value: datetime):
        with open(self.file_path, mode="w") as f:
            f.write(str(value.timestamp()))

    def wait(self):
        lct = self.get()
        next_call_time = lct + timedelta(seconds=self.niceness)
        now = datetime.now()
        if next_call_time < now:
            self.set(now)
            return
        self.set(next_call_time)
        wait_time = (next_call_time - now).total_seconds()
        wait(wait_time)


FILE_PATH = os.path.join(LEXPATH, "last_eurlex_call_time")

eurlex_request_queue = ServiceRequestDoorkeeper(FILE_PATH, 1)

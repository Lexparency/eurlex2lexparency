import os
import unittest
from math import ceil
from unittest import mock

from eurlex2lexparency.utils.eurlex_request_lock import eurlex_request_queue


class TestRequestLock(unittest.TestCase):
    def setUp(self) -> None:
        try:
            os.remove(eurlex_request_queue.file_path)
        except FileNotFoundError:
            pass

    def test(self):
        lct_init = eurlex_request_queue.get()
        with mock.patch("eurlex2lexparency.utils.eurlex_request_lock.wait") as _:
            # mock is just to avoid actual waiting
            eurlex_request_queue.wait()
            eurlex_request_queue.wait()
            eurlex_request_queue.wait()
            eurlex_request_queue.wait()
        lct_final = eurlex_request_queue.get()
        self.assertEqual(
            4 * eurlex_request_queue.niceness,
            ceil((lct_final - lct_init).total_seconds()),
        )


if __name__ == "__main__":
    unittest.main()

import base64
from abc import ABCMeta, abstractmethod
from collections.__init__ import namedtuple
from functools import lru_cache


class Retriever(metaclass=ABCMeta):
    def __init__(self, local_path, url):
        self.url = url
        self.local_path = local_path

    @property
    @lru_cache(maxsize=1)
    def document(self):
        try:
            return self.open()
        except (FileNotFoundError, OSError):
            return self.retrieve()

    @abstractmethod
    def open(self):
        pass

    @abstractmethod
    def retrieve(self):
        pass


class FormatsNotLoaded(Exception):
    pass


class FormatNotAvailable(Exception):
    pass


Formats = namedtuple("Formats", ["html", "pdf"])


def img_2_base64(suffix, src):
    encoded = base64.b64encode(src)
    return f"data:image/{suffix};base64, " + encoded.decode("ascii")

import datetime
import functools
import logging
import os
import sys
from collections import namedtuple
from datetime import date, timedelta
from logging import handlers
from time import sleep


def retry(exceptions, tries=2, wait=None):
    """Decorator factory creates retry-decorators which repeats the function
    execution until it finally executes without throwing an exception
    or until the max number of attempts <tries> is reached.
    If <wait> is provided, the process waits that amount of seconds before
    going for the next attempt.
    """

    def decorator(f):
        @functools.wraps(f)
        def protegee(*args, **kwargs):
            for attempt in range(tries):
                try:
                    return f(*args, **kwargs)
                except exceptions:
                    if attempt == tries - 1:  # Exception in final attempt
                        raise
                    if wait is not None:
                        sleep(wait)

        return protegee

    return decorator


def get_fallbacker(logger, default=None, exceptions=RuntimeError):
    """copied from the interface (doq) !!!"""

    def fallbacker_(f):
        @functools.wraps(f)
        def fallbacked(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except exceptions:
                logger.error(
                    "Failed executing {}.{}\n"
                    "Positional arguments: {}\nKeyword arguments: {}".format(
                        f.__module__,
                        f.__name__,
                        ", ".join(map(str, args)),
                        ", ".join(
                            [
                                "({}, {})".format(str(k), str(v))
                                for k, v in kwargs.items()
                            ]
                        ),
                    ),
                    exc_info=True,
                )
                if callable(default):
                    return default(*args, **kwargs)
                return default

        return fallbacked

    return fallbacker_


def _seconds_until_tomorrow():
    now = datetime.datetime.now()
    time_of_awakening = datetime.datetime.combine(
        (now + datetime.timedelta(1)).date(), datetime.time(0, 0)
    )
    return (time_of_awakening - now).seconds


def wait_until_tomorrow(goodwill=0):
    """Does what it name says it does.
    :param goodwill: Some extra minutes to wait, to make sure everybody agrees
        that the next day has arrived.
    """
    sleep(_seconds_until_tomorrow() + goodwill * 60)


def get_file_content(file_path, **kwargs):
    with open(file_path, **kwargs) as f:
        return f.read()


class TwoWay:
    def __init__(self, names, pair_list=None):
        """
        :param names: tuple of strings, meaning the names of each "column"
        :param pair_list: List of tuples
        """
        self.left_name, self.right_name = names
        self.d = {names[0]: dict(), names[1]: dict()}
        for l, r in pair_list or tuple():
            self.set(**{self.left_name: l, self.right_name: r})

    def keys(self, column):
        return self.d[column].keys()

    def set(self, **kw):
        self.d[self.left_name][kw[self.left_name]] = kw[self.right_name]
        self.d[self.right_name][kw[self.right_name]] = kw[self.left_name]

    def get(self, **kwargs):
        key, value = list(kwargs.items())[0]
        return self.d[key][value]

    def __repr__(self):
        return 'TwoWay(("{}", "{}"), {})'.format(
            self.left_name,
            self.right_name,
            str(list((left, right) for left, right in self.d[self.left_name].items())),
        )

    def items(self):
        return self.d[self.left_name].items()


class FullMonth(namedtuple("FM", ["year", "month"])):
    @property
    def ultimo(self) -> date:
        return self.next().first - timedelta(1)

    @property
    def first(self) -> date:
        return date(self.year, self.month, 1)

    def next(self):
        if self.month == 12:
            return FullMonth(self.year + 1, 1)
        return FullMonth(self.year, self.month + 1)

    def previous(self):
        if self.month == 1:
            return FullMonth(self.year - 1, 12)
        return FullMonth(self.year, self.month - 1)

    @classmethod
    def instantiate(cls, v):
        if type(v) is str:
            try:
                return cls(int(v[0:4]), int(v[4:6]))
            except IndexError:
                raise ValueError(f"Could not parse {v} as FullMonth")
        if type(v) is date:
            return cls(v.year, v.month)


class SwingingFileLogger(logging.Logger):
    formatter = logging.Formatter(
        "%(levelname)s %(asctime)s %(module)s.%(funcName)s: %(message)s"
    )

    _instance = None

    @classmethod
    def get(cls, name, file_path=None):
        self = cls._instance or cls("sfl", logging.INFO)
        if cls._instance is None:
            cls._instance = self
        for handler in self.handlers[:]:
            self.removeHandler(handler)
        self.addHandler(cls.get_handler(name, file_path))
        return self

    @classmethod
    def get_handler(cls, name, file_path=None):
        if file_path:
            handler = handlers.TimedRotatingFileHandler(
                os.path.join(file_path, "{}.log".format(name)),
                interval=4,
                backupCount=5,
                encoding="utf-8",
            )
        else:
            handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        handler.setFormatter(cls.formatter)
        return handler

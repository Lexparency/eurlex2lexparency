import unittest

from eurlex2lexparency.utils.generics import retry


class DummyFunction:
    def __init__(self, raises=0):
        self.raises = raises
        self._call_count = 0

    def __call__(self):
        self._call_count += 1
        if self._call_count >= self.raises + 1:
            return True
        raise RuntimeError(f"Attempt number {self._call_count}. Try again!")


class TestRetry(unittest.TestCase):
    def setUp(self):
        self.dfs = [DummyFunction(k) for k in range(5)]
        self.decorateds = [retry(RuntimeError, 2)(df) for df in self.dfs]

    def test_dummy_function(self):
        """Just testing the DummyFunciton class."""
        for i, df in enumerate(self.dfs):
            for n in range(i):
                self.assertRaises(RuntimeError, df)
            self.assertTrue(df())
            self.assertTrue(df())

    def test_retry(self):
        for i, df in enumerate(self.decorateds):
            if i >= 2:
                self.assertRaises(RuntimeError, df)
            else:
                self.assertTrue(df())
                self.assertTrue(df())


if __name__ == "__main__":
    unittest.main()

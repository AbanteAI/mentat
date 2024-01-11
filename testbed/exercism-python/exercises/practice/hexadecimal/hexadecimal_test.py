# To avoid trivial solutions, try to solve this problem without the
# function int(s, base=16)

import unittest

from hexadecimal import hexa


class HexadecimalTest(unittest.TestCase):
    def test_valid_hexa1(self):
        self.assertEqual(hexa('1'), 1)

    def test_valid_hexa2(self):
        self.assertEqual(hexa('c'), 12)

    def test_valid_hexa3(self):
        self.assertEqual(hexa('10'), 16)

    def test_valid_hexa4(self):
        self.assertEqual(hexa('af'), 175)

    def test_valid_hexa5(self):
        self.assertEqual(hexa('100'), 256)

    def test_valid_hexa6(self):
        self.assertEqual(hexa('19ACE'), 105166)

    def test_valid_hexa7(self):
        self.assertEqual(hexa('000000'), 0)

    def test_valid_hexa8(self):
        self.assertEqual(hexa('ffff00'), 16776960)

    def test_valid_hexa9(self):
        self.assertEqual(hexa('00fff0'), 65520)

    def test_invalid_hexa(self):
        with self.assertRaisesWithMessage(ValueError):
            hexa('carrot')

    # Utility functions
    def assertRaisesWithMessage(self, exception):
        return self.assertRaisesRegex(exception, r".+")


if __name__ == '__main__':
    unittest.main()

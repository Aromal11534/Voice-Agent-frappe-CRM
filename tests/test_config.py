import unittest

from app.config import is_configured


class ConfigurationTests(unittest.TestCase):
    def test_placeholders_are_not_configured(self):
        self.assertFalse(is_configured("your_api_key"))
        self.assertFalse(is_configured(""))
        self.assertFalse(is_configured("real-value", "replace_me"))

    def test_real_values_are_configured(self):
        self.assertTrue(is_configured("real-key", "real-secret"))


if __name__ == "__main__":
    unittest.main()

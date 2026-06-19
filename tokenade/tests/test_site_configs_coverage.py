import unittest

from tokenade.core.importer.site_configs import list_sites, get_site_config


class TestSiteConfigsCoverage(unittest.TestCase):
    def test_list_sites_returns_list(self):
        result = list_sites()
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_list_sites_contains_known_sites(self):
        result = list_sites()
        self.assertIn("github", result)
        self.assertIn("google", result)

    def test_get_site_config_unknown(self):
        result = get_site_config("nonexistent_site_xyz")
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()

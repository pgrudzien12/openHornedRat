import json
from pathlib import Path
import tempfile
import unittest

from whshr import catalog
from whshr.assets import AssetId, AssetLocator
from whshr.cache import AssetCache


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self._write("FILE/SCRIPT/Bf001.BTS", b"[BATTLESCRIPT]\n[END]\n")
        self._write("REMOTE/BINARY/ANIM/Intro.SI", b"RIFF")
        self._write("FILE/BINARY/STANDARD.PAL", b"file palette")
        self._write("UPDATE/BINARY/standard.pal", b"updated palette")

    def tearDown(self):
        self.temporary.cleanup()

    def _write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def test_given_installation_when_catalogued_then_ids_are_stable_and_update_assets_win(self):
        assets = catalog.build(self.root)

        self.assertEqual(
            [str(record.identifier) for record in assets.records],
            ["vanilla:battle/bf001", "vanilla:cutscene/intro", "vanilla:palette/standard"],
        )
        self.assertEqual(assets.get("vanilla:cutscene/intro").decoder, "omni-si")
        self.assertEqual(
            assets.resolve(self.root, "vanilla:palette/standard"),
            self.root / "UPDATE/BINARY/standard.pal",
        )

    def test_given_installation_when_catalog_is_written_then_it_contains_metadata_not_asset_contents(self):
        output = self.root / "cache/catalog.json"
        assets = catalog.write(self.root, output)
        data = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(data["version"], catalog.CATALOG_VERSION)
        self.assertEqual(len(data["assets"]), len(assets.records))
        self.assertNotIn("updated palette", output.read_text(encoding="utf-8"))
        self.assertEqual(data["assets"][0]["fingerprint"]["size"], 21)

    def test_given_catalog_json_when_read_then_logical_ids_still_resolve_original_assets(self):
        output = self.root / "cache/catalog.json"
        catalog.write(self.root, output)

        reloaded = catalog.read(output)

        self.assertEqual(
            reloaded.resolve(self.root, AssetId("vanilla", "battle", "bf001")),
            self.root / "FILE/SCRIPT/Bf001.BTS",
        )

    def test_given_unchanged_asset_when_requested_twice_then_loader_runs_once(self):
        assets = catalog.build(self.root)
        locator = AssetLocator(self.root)
        cache = AssetCache()
        calls = []

        def load(_, path):
            calls.append(path)
            return path.read_bytes()

        first = cache.get(locator, assets, "vanilla:palette/standard", load)
        second = cache.get(locator, assets, "vanilla:palette/standard", load)

        self.assertEqual((first, second), (b"updated palette", b"updated palette"))
        self.assertEqual(calls, [self.root / "UPDATE/BINARY/standard.pal"])

    def test_given_changed_original_asset_when_requested_then_cache_reloads_it(self):
        assets = catalog.build(self.root)
        locator = AssetLocator(self.root)
        cache = AssetCache()
        calls = []
        source = self.root / "UPDATE/BINARY/standard.pal"

        def load(_, path):
            calls.append(path.read_bytes())
            return path.read_bytes()

        cache.get(locator, assets, "vanilla:palette/standard", load)
        source.write_bytes(b"changed palette with a different size")
        result = cache.get(locator, assets, "vanilla:palette/standard", load)

        self.assertEqual(result, b"changed palette with a different size")
        self.assertEqual(calls, [b"updated palette", b"changed palette with a different size"])

    def test_given_unsafe_asset_path_when_locator_resolves_it_then_it_is_rejected(self):
        locator = AssetLocator(self.root)

        with self.assertRaisesRegex(ValueError, "relative path"):
            locator.resolve("file", "../outside")

    def test_given_original_developer_battle_name_when_used_as_an_asset_id_then_it_is_supported(self):
        identifier = AssetId("vanilla", "battle", "_destest")

        self.assertEqual(str(identifier), "vanilla:battle/_destest")


if __name__ == "__main__":
    unittest.main()

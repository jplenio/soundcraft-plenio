"""Tests of the add-in's own routes that need no ComfyUI: the model answer and the vendor record.

    python -I addins/plenio/backend/tests/test_routes.py
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

# The copy of Plenio stays as it was copied: no bytecode caches in it.
sys.dont_write_bytecode = True

ADDIN = Path(__file__).resolve().parents[2]
VENDOR = ADDIN / "vendor" / "plenio"
sys.path.insert(0, str(VENDOR))

from plenio.core import models  # noqa: E402  (the copied Plenio)


def load_routes():
    spec = importlib.util.spec_from_file_location("scp_routes", ADDIN / "backend" / "soundcraft_plenio" / "routes.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


routes = load_routes()


class WarpAnswer(unittest.TestCase):
    def test_an_estimate_is_passed_on_and_no_estimate_is_said(self) -> None:
        self.assertEqual(routes.warp_answer(None), {"warp": None})
        found = {"warp": [1.0, -1.3], "anchors": [[1.0, 2.3]], "match": 0.35, "lead": 2.31}
        self.assertEqual(routes.warp_answer(found), {"warp": [1.0, -1.3], "match": 0.35, "lead": 2.31})


class ModelsAnswer(unittest.TestCase):
    def setUp(self) -> None:
        self.catalogue = models.load_catalogue(VENDOR / "resources" / "models.toml")

    def answer(self, installed: set[str]):
        def locate(folder: str, file: str) -> Path | None:
            return Path("/models", folder, file) if file in installed else None

        def target(folder: str) -> Path | None:
            return Path("/models", folder)

        sizes = {m.file: m.bytes for m in self.catalogue.values()}

        def take_inventory(catalogue, locate_fn):
            found = {m.file: sizes[m.file] for m in catalogue.values() if locate_fn(m.folder, m.file)}
            return models.Inventory(found)

        return routes.models_answer(self.catalogue, locate, target, models.readiness, take_inventory)

    def test_minimax_is_left_out_everywhere(self) -> None:
        answer = self.answer(set())
        self.assertTrue(answer["models"])
        for model in answer["models"]:
            self.assertNotIn("minimax", model["id"])
            self.assertFalse(any("MiniMax" in t for t in model["templates"] + model["optional_templates"]))
        self.assertEqual(set(answer["templates"]), {"yue2-song", "yue2-cover", "yue2-daw"})

    def test_a_missing_model_says_where_it_goes_and_what_it_holds_up(self) -> None:
        answer = self.answer(set())
        yue2 = next(m for m in answer["models"] if m["id"] == "yue2-3b-int8")
        self.assertEqual(yue2["status"], "missing")
        self.assertIsNone(yue2["path"])
        self.assertTrue(yue2["target"].replace("\\", "/").endswith("checkpoints/yue2_3b_int8_convrot.safetensors"))
        self.assertTrue(yue2["non_commercial"])
        song = answer["templates"]["yue2-song"]
        self.assertFalse(song["ready"])
        self.assertIn("yue2-3b-int8", song["missing"])
        self.assertGreater(song["missing_bytes"], 0)

    def test_with_every_model_installed_the_templates_are_ready(self) -> None:
        answer = self.answer({m.file for m in self.catalogue.values()})
        self.assertTrue(all(t["ready"] for t in answer["templates"].values()))
        self.assertTrue(all(m["status"] == "installed" for m in answer["models"]))


class VendorInfo(unittest.TestCase):
    def test_the_sync_record_is_read(self) -> None:
        info = routes.vendor_info((ADDIN / "vendor" / "VENDOR.toml").read_text(encoding="utf-8"))
        self.assertEqual(len(info["commit"]), 40)
        self.assertEqual(info["version"], "1.5.0")


if __name__ == "__main__":
    unittest.main()

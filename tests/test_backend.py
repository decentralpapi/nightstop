"""Optional FastAPI route test; skips cleanly when fastapi/httpx are not installed."""
import importlib.util
import json
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@unittest.skipUnless(importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx"), "optional FastAPI/httpx not installed")
class BackendTests(unittest.TestCase):
    def load(self):
        spec = importlib.util.spec_from_file_location("nightstop_api_test", ROOT / "dashboard" / "plugin_api.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_routes(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        mod = self.load()
        app = FastAPI()
        app.include_router(mod.router, prefix="/api/plugins/nightstop")
        with patch.object(mod, "plan_night", return_value=json.dumps({"data": {"kind": "night"}})) as h:
            with TestClient(app) as c:
                r = c.post("/api/plugins/nightstop/night", json={"origin": "Lisbon airport"})
        self.assertEqual(r.json()["data"]["kind"], "night")
        h.assert_called_once()

    def test_bad_input_is_json_error(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        app = FastAPI()
        app.include_router(self.load().router)
        with TestClient(app) as c:
            r = c.post("/ride", json={"pickup": ""})
        self.assertIn("error", r.json())
        self.assertIsNone(r.json()["data"])

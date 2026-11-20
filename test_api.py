import copy
import json
import threading
import unittest
import urllib.error
import urllib.request

from app import make_server
from solver import evaluate

with open("sample_input.json") as f:
    SAMPLE = json.load(f)


class ApiTests(unittest.TestCase):
    def runTest(self):          # lets setUpClass build an instance to reuse call()
        pass

    @classmethod
    def setUpClass(cls):
        cls.server = make_server("127.0.0.1", 0)          # port 0 = any free port
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.sample_code, cls.sample_out = cls().call(body=SAMPLE)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def call(self, path="/api/roster", body=None, method="POST"):
        raw = body if isinstance(body, bytes) else json.dumps(body).encode()
        request = urllib.request.Request(self.url + path, data=raw if method == "POST" else None,
                                         method=method)
        try:
            with urllib.request.urlopen(request) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())

    def test_ok_gives_200_and_consistent_totals(self):
        code, out = self.sample_code, self.sample_out
        self.assertEqual(code, 200)
        self.assertEqual(out["status"], "ok")
        roster = {int(row["hour"][:2]) - 10: row["powered"] for row in out["roster"]}
        check = evaluate(SAMPLE, roster)
        self.assertEqual(check["violations"], [])
        self.assertEqual(out["value_total"], check["value"])
        self.assertEqual(round(out["fuel_total_litres"] * 100), check["fuel_hundredths"])
        self.assertEqual(out["dark_hours"], check["dark_hours"])

    def test_every_outage_hour_once_and_every_shop_once(self):
        out = self.sample_out
        self.assertEqual([r["hour"] for r in out["roster"]],
                         ["12:00", "13:00", "14:00", "15:00", "17:00", "18:00", "19:00"])
        ids = sorted(s["id"] for s in SAMPLE["shops"])
        for row in out["roster"]:
            listed = row["powered"] + [d["id"] for d in row["dark"]]
            self.assertEqual(sorted(listed), ids)
            for d in row["dark"]:
                self.assertTrue(d["reason"])

    def test_infeasible_is_still_200(self):
        data = copy.deepcopy(SAMPLE)
        data["fuel_budget_litres"] = 5.0
        code, out = self.call(body=data)
        self.assertEqual(code, 200)
        self.assertEqual(out["status"], "infeasible")
        self.assertIn("fuel", out["reason"])

    def test_invalid_input_is_400_and_names_the_field(self):
        data = copy.deepcopy(SAMPLE)
        data["shops"][1]["id"] = "pharmacy"
        code, out = self.call(body=data)
        self.assertEqual(code, 400)
        self.assertEqual(out["status"], "invalid_input")
        self.assertIn("shops[1].id", out["message"])

    def test_bad_json_is_400(self):
        code, out = self.call(body=b"{not json")
        self.assertEqual(code, 400)
        self.assertEqual(out["status"], "invalid_input")

    def test_infinity_is_400(self):
        code, out = self.call(body=b'{"fuel_budget_litres": Infinity}')
        self.assertEqual(code, 400)

    def test_no_outage_day(self):
        data = copy.deepcopy(SAMPLE)
        data["grid_available"] = [True] * 10
        code, out = self.call(body=data)
        self.assertEqual(code, 200)
        self.assertEqual(out["roster"], [])
        self.assertEqual(out["value_total"], 0)
        self.assertEqual(out["fuel_total_litres"], 0)

    def test_wrong_path_and_wrong_method(self):
        self.assertEqual(self.call("/nope", body={}, method="POST")[0], 404)
        self.assertEqual(self.call("/api/roster", method="GET")[0], 405)


if __name__ == "__main__":
    unittest.main()
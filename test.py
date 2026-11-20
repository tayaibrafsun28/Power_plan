import itertools
import random
import copy
import json
import unittest

from solver import InvalidInput, evaluate, fuel_cost, optimize, outage_hours, validate

with open("sample_input.json") as f:
    SAMPLE = json.load(f)


def broken(change):
    """Return a copy of the sample with one change applied."""
    data = copy.deepcopy(SAMPLE)
    change(data)
    return data


class ValidateTests(unittest.TestCase):
    def test_sample_is_valid(self):
        validate(SAMPLE)

    def test_no_shops_is_valid(self):
        validate(broken(lambda d: d.update(shops=[])))

    def test_missing_field(self):
        data = broken(lambda d: d.pop("fuel_table"))
        with self.assertRaisesRegex(InvalidInput, "fuel_table"):
            validate(data)

    def test_grid_wrong_length(self):
        data = broken(lambda d: d.update(grid_available=[True] * 9))
        with self.assertRaisesRegex(InvalidInput, "grid_available"):
            validate(data)

    def test_capacity_not_positive(self):
        data = broken(lambda d: d.update(generator_capacity_kw=0))
        with self.assertRaisesRegex(InvalidInput, "generator_capacity_kw"):
            validate(data)

    def test_fuel_budget_three_decimals(self):
        data = broken(lambda d: d.update(fuel_budget_litres=17.005))
        with self.assertRaisesRegex(InvalidInput, "fuel_budget_litres"):
            validate(data)

    def test_fuel_budget_negative(self):
        data = broken(lambda d: d.update(fuel_budget_litres=-1))
        with self.assertRaisesRegex(InvalidInput, "fuel_budget_litres"):
            validate(data)

    def test_fuel_table_not_increasing(self):
        data = broken(lambda d: d["fuel_table"][1].update(load_kw=7))
        with self.assertRaisesRegex(InvalidInput, "fuel_table"):
            validate(data)

    def test_fuel_table_last_level_not_capacity(self):
        data = broken(lambda d: d["fuel_table"][2].update(load_kw=19))
        with self.assertRaisesRegex(InvalidInput, "last load_kw"):
            validate(data)

    def test_duplicate_shop_id(self):
        data = broken(lambda d: d["shops"][1].update(id="pharmacy"))
        with self.assertRaisesRegex(InvalidInput, "duplicate"):
            validate(data)

    def test_blank_shop_id(self):
        data = broken(lambda d: d["shops"][0].update(id="  "))
        with self.assertRaisesRegex(InvalidInput, "id"):
            validate(data)

    def test_bad_shop_type(self):
        data = broken(lambda d: d["shops"][0].update(type="vip"))
        with self.assertRaisesRegex(InvalidInput, "type"):
            validate(data)

    def test_shop_value_list_wrong_length(self):
        data = broken(lambda d: d["shops"][2].update(value_per_slot=[1, 2, 3]))
        with self.assertRaisesRegex(InvalidInput, "value_per_slot"):
            validate(data)

    def test_negative_shop_value(self):
        data = broken(lambda d: d["shops"][2]["value_per_slot"].__setitem__(0, -1))
        with self.assertRaisesRegex(InvalidInput, "value_per_slot"):
            validate(data)

    def test_too_many_shops(self):
        def add_shop(d):
            extra = copy.deepcopy(d["shops"][-1])
            extra["id"] = "thirteenth"
            d["shops"].append(extra)
        with self.assertRaisesRegex(InvalidInput, "at most 12"):
            validate(broken(add_shop))

    def test_not_an_object(self):
        with self.assertRaises(InvalidInput):
            validate([1, 2, 3])


# Small worked example from the original problem statement:
# the best roster scores 84 and uses exactly 8.00 L.
SMALL = {
    "grid_available": [True, True, False, False, False, True, True, False, False, False],
    "generator_capacity_kw": 10,
    "fuel_budget_litres": 8.00,
    "fuel_table": [{"load_kw": 4, "litres_per_hour": 0.80},
                   {"load_kw": 7, "litres_per_hour": 1.20},
                   {"load_kw": 10, "litres_per_hour": 1.60}],
    "max_consecutive_dark": 2,
    "shops": [
        {"id": "pharmacy", "kw": 3, "type": "mandatory", "value_per_slot": [5] * 10},
        {"id": "tailor", "kw": 4, "type": "normal", "value_per_slot": [2, 2, 3, 3, 4, 4, 4, 4, 5, 5]},
        {"id": "mobile", "kw": 3, "type": "normal", "value_per_slot": [1, 1, 2, 2, 2, 3, 4, 6, 8, 8]},
        {"id": "photocopy", "kw": 2, "type": "normal", "value_per_slot": [3, 3, 5, 5, 4, 3, 2, 2, 1, 1]},
        {"id": "tea_stall", "kw": 1, "type": "normal", "value_per_slot": [2, 2, 2, 3, 3, 2, 2, 3, 3, 3]},
    ],
}
BEST_SMALL = {
    2: ["pharmacy", "mobile", "photocopy", "tea_stall"],
    3: ["pharmacy", "tailor", "photocopy", "tea_stall"],
    4: ["pharmacy", "tea_stall"],
    7: ["pharmacy", "tailor", "photocopy", "tea_stall"],
    8: ["pharmacy", "mobile", "tea_stall"],
    9: ["pharmacy", "mobile", "tea_stall"],
}


class FuelTests(unittest.TestCase):
    table = SMALL["fuel_table"]

    def test_zero_load_is_free(self):
        self.assertEqual(fuel_cost(0, self.table), 0)

    def test_rounds_up_to_next_level(self):
        self.assertEqual(fuel_cost(1, self.table), 80)
        self.assertEqual(fuel_cost(4, self.table), 80)
        self.assertEqual(fuel_cost(5, self.table), 120)
        self.assertEqual(fuel_cost(10, self.table), 160)

    def test_over_capacity(self):
        with self.assertRaises(ValueError):
            fuel_cost(11, self.table)

    def test_outage_hours(self):
        self.assertEqual(outage_hours(SMALL), [2, 3, 4, 7, 8, 9])


class EvaluateTests(unittest.TestCase):
    def test_worked_example_scores_84_and_8_litres(self):
        result = evaluate(SMALL, BEST_SMALL)
        self.assertEqual(result["violations"], [])
        self.assertEqual(result["value"], 84)
        self.assertEqual(result["fuel_hundredths"], 800)

    def test_dark_hours_counted(self):
        result = evaluate(SMALL, BEST_SMALL)
        self.assertEqual(result["dark_hours"]["tailor"], 4)
        self.assertEqual(result["dark_hours"]["tea_stall"], 0)

    def test_over_capacity_is_caught(self):
        roster = copy.deepcopy(BEST_SMALL)
        roster[3] = ["pharmacy", "tailor", "mobile", "photocopy", "tea_stall"]   # 13 kW
        result = evaluate(SMALL, roster)
        self.assertTrue(any("capacity" in v for v in result["violations"]))

    def test_over_fuel_budget_is_caught(self):
        roster = copy.deepcopy(BEST_SMALL)
        roster[4] = ["pharmacy", "tailor", "photocopy", "tea_stall"]   # +0.80 L -> 8.80 L
        result = evaluate(SMALL, roster)
        self.assertTrue(any("fuel" in v for v in result["violations"]))

    def test_mandatory_shop_dark_is_caught(self):
        roster = copy.deepcopy(BEST_SMALL)
        roster[4] = ["tea_stall"]
        result = evaluate(SMALL, roster)
        self.assertTrue(any("mandatory" in v for v in result["violations"]))

    def test_three_dark_hours_in_a_row_is_caught(self):
        roster = copy.deepcopy(BEST_SMALL)
        roster[7] = ["pharmacy", "tea_stall"]          # tailor dark 17, 18, 19
        roster[8] = ["pharmacy", "tea_stall"]
        roster[9] = ["pharmacy", "tea_stall"]
        result = evaluate(SMALL, roster)
        self.assertTrue(any("dark run: tailor" in v for v in result["violations"]))

    def test_grid_hour_resets_the_run(self):
        # dark at hours 2 and 3 (outage), grid hours 5-6 reset, dark again 7, 8: allowed
        roster = copy.deepcopy(BEST_SMALL)
        roster[2] = ["pharmacy", "photocopy", "tea_stall"]
        roster[3] = ["pharmacy", "photocopy", "tea_stall"]
        roster[4] = ["pharmacy", "tailor", "tea_stall"]
        roster[7] = ["pharmacy", "photocopy", "tea_stall"]
        roster[8] = ["pharmacy", "photocopy", "tea_stall"]
        roster[9] = ["pharmacy", "tailor", "tea_stall"]
        result = evaluate(SMALL, roster)
        self.assertFalse(any("dark run: tailor" in v for v in result["violations"]))

    def test_missing_hour_is_caught(self):
        roster = copy.deepcopy(BEST_SMALL)
        del roster[9]
        result = evaluate(SMALL, roster)
        self.assertTrue(any("no decision" in v for v in result["violations"]))

    def test_unknown_shop_is_caught(self):
        roster = copy.deepcopy(BEST_SMALL)
        roster[4] = ["pharmacy", "ghost"]
        result = evaluate(SMALL, roster)
        self.assertTrue(any("unknown" in v for v in result["violations"]))


def brute_force(data):
    """Try every possible roster. Slow, only for tiny inputs. Returns best value or None."""
    ids = [s["id"] for s in data["shops"]]
    subsets = [[i for k, i in enumerate(ids) if mask >> k & 1] for mask in range(1 << len(ids))]
    outages = outage_hours(data)
    best = None
    for combo in itertools.product(subsets, repeat=len(outages)):
        roster = dict(zip(outages, combo))
        result = evaluate(data, roster)
        if not result["violations"] and (best is None or result["value"] > best):
            best = result["value"]
    return best


def random_input(rng):
    capacity = rng.randint(4, 8)
    levels = sorted(rng.sample(range(1, capacity), rng.randint(0, 2))) + [capacity]
    litres = 0
    table = []
    for kw in levels:
        litres += rng.randint(50, 150)
        table.append({"load_kw": kw, "litres_per_hour": litres / 100})
    shops = []
    for k in range(rng.randint(2, 4)):
        shops.append({
            "id": f"s{k}", "kw": rng.randint(1, 4),
            "type": "mandatory" if rng.random() < 0.25 else "normal",
            "value_per_slot": [rng.randint(0, 9) for _ in range(10)]})
    grid = [True] * 10
    for h in rng.sample(range(10), rng.randint(0, 3)):
        grid[h] = False
    return {"grid_available": grid, "generator_capacity_kw": capacity,
            "fuel_budget_litres": rng.randint(100, 600) / 100, "fuel_table": table,
            "max_consecutive_dark": rng.randint(0, 2), "shops": shops}


class OptimizeTests(unittest.TestCase):
    def test_worked_example_best_is_84_and_8_litres(self):
        result = optimize(SMALL)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["value"], 84)
        self.assertEqual(result["fuel_hundredths"], 800)
        self.assertEqual(evaluate(SMALL, result["roster"])["violations"], [])

    def test_real_sample_has_no_violations(self):
        result = optimize(SAMPLE)
        self.assertEqual(result["status"], "ok")
        check = evaluate(SAMPLE, result["roster"])
        self.assertEqual(check["violations"], [])
        self.assertEqual(check["value"], result["value"])
        self.assertEqual(check["fuel_hundredths"], result["fuel_hundredths"])
        self.assertLessEqual(result["fuel_hundredths"], 1700)

    def test_no_outage_gives_empty_roster(self):
        data = broken(lambda d: d.update(grid_available=[True] * 10))
        result = optimize(data)
        self.assertEqual(result, {"status": "ok", "roster": {}, "value": 0, "fuel_hundredths": 0})

    def test_no_shops(self):
        result = optimize(broken(lambda d: d.update(shops=[])))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["value"], 0)

    def test_mandatory_shops_too_big_for_generator(self):
        data = broken(lambda d: d["shops"][0].update(kw=19))      # 19 + 2 > 20 kW
        result = optimize(data)
        self.assertEqual(result["status"], "infeasible")
        self.assertIn("capacity", result["reason"])

    def test_mandatory_shops_need_more_fuel_than_budget(self):
        data = broken(lambda d: d.update(fuel_budget_litres=5.0))   # 7 hours x 1.20 L = 8.40 L
        result = optimize(data)
        self.assertEqual(result["status"], "infeasible")
        self.assertIn("fuel", result["reason"])

    def test_dark_limit_cannot_be_met(self):
        # a normal shop too big for the generator can never be on, but 4 outage hours
        # in a row would leave it dark for more than 2 hours
        data = broken(lambda d: d["shops"][2].update(kw=19))
        result = optimize(data)
        self.assertEqual(result["status"], "infeasible")

    def test_matches_brute_force_on_random_inputs(self):
        rng = random.Random(2026)
        for case in range(150):
            data = random_input(rng)
            expected = brute_force(data)
            result = optimize(data)
            if expected is None:
                self.assertEqual(result["status"], "infeasible", f"case {case}")
            else:
                self.assertEqual(result["status"], "ok", f"case {case}")
                self.assertEqual(result["value"], expected, f"case {case}")
                self.assertEqual(evaluate(data, result["roster"])["violations"], [], f"case {case}")


if __name__ == "__main__":
    unittest.main()
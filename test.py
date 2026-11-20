import copy
import json
import unittest

from solver import InvalidInput, evaluate, fuel_cost, outage_hours, validate

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


if __name__ == "__main__":
    unittest.main()
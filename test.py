import copy
import json
import unittest

from solver import InvalidInput, validate

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


if __name__ == "__main__":
    unittest.main()
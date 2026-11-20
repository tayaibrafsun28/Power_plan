"""Power_plan solver: decides which shops get generator power."""

from decimal import Decimal

HOURS = 10          # slots 0-9 = 10:00 to 20:00
MAX_SHOPS = 12


class InvalidInput(Exception):
    """Raised when the input JSON does not match the expected format."""


def to_hundredths(value, field):
    """Convert litres (e.g. 1.2) to whole hundredths (120). Max 2 decimals."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidInput(f"{field}: must be a number")
    if value < 0:
        raise InvalidInput(f"{field}: must not be negative")
    hundredths = Decimal(str(value)) * 100
    if hundredths != hundredths.to_integral_value():
        raise InvalidInput(f"{field}: more than two decimal places")
    return int(hundredths)


def _is_whole(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate(data):
    """Check the input. Returns nothing if fine, raises InvalidInput if not."""
    if not isinstance(data, dict):
        raise InvalidInput("input: must be a JSON object")

    for key in ("grid_available", "generator_capacity_kw", "fuel_budget_litres",
                "fuel_table", "max_consecutive_dark", "shops"):
        if key not in data:
            raise InvalidInput(f"{key}: missing")

    grid = data["grid_available"]
    if not isinstance(grid, list) or len(grid) != HOURS:
        raise InvalidInput(f"grid_available: must be a list of {HOURS} true/false values")
    if not all(isinstance(g, bool) for g in grid):
        raise InvalidInput("grid_available: every entry must be true or false")

    capacity = data["generator_capacity_kw"]
    if not _is_whole(capacity) or capacity <= 0:
        raise InvalidInput("generator_capacity_kw: must be a positive whole number")

    to_hundredths(data["fuel_budget_litres"], "fuel_budget_litres")

    mcd = data["max_consecutive_dark"]
    if not _is_whole(mcd) or mcd < 0:
        raise InvalidInput("max_consecutive_dark: must be a whole number, 0 or more")

    _validate_fuel_table(data["fuel_table"], capacity)
    _validate_shops(data["shops"])


def _validate_fuel_table(table, capacity):
    if not isinstance(table, list) or not table:
        raise InvalidInput("fuel_table: must be a non-empty list")
    previous = 0
    for i, level in enumerate(table):
        where = f"fuel_table[{i}]"
        if not isinstance(level, dict):
            raise InvalidInput(f"{where}: must be an object")
        kw = level.get("load_kw")
        if not _is_whole(kw) or kw <= previous:
            raise InvalidInput(f"{where}.load_kw: must be a whole number, higher than the previous level")
        if "litres_per_hour" not in level:
            raise InvalidInput(f"{where}.litres_per_hour: missing")
        to_hundredths(level["litres_per_hour"], f"{where}.litres_per_hour")
        previous = kw
    if previous != capacity:
        raise InvalidInput("fuel_table: last load_kw must equal generator_capacity_kw")


def _validate_shops(shops):
    if not isinstance(shops, list):
        raise InvalidInput("shops: must be a list")
    if len(shops) > MAX_SHOPS:
        raise InvalidInput(f"shops: at most {MAX_SHOPS} shops allowed")
    seen = set()
    for i, shop in enumerate(shops):
        where = f"shops[{i}]"
        if not isinstance(shop, dict):
            raise InvalidInput(f"{where}: must be an object")
        sid = shop.get("id")
        if not isinstance(sid, str) or not sid.strip():
            raise InvalidInput(f"{where}.id: must be a non-blank text")
        if sid in seen:
            raise InvalidInput(f"{where}.id: duplicate id '{sid}'")
        seen.add(sid)
        if not _is_whole(shop.get("kw")) or shop["kw"] <= 0:
            raise InvalidInput(f"{where}.kw: must be a positive whole number")
        if shop.get("type") not in ("mandatory", "normal"):
            raise InvalidInput(f"{where}.type: must be 'mandatory' or 'normal'")
        values = shop.get("value_per_slot")
        if not isinstance(values, list) or len(values) != HOURS:
            raise InvalidInput(f"{where}.value_per_slot: must be a list of {HOURS} numbers")
        if not all(_is_whole(v) and v >= 0 for v in values):
            raise InvalidInput(f"{where}.value_per_slot: every value must be a whole number, 0 or more")


# ---------------------------------------------------------------- fuel

def fuel_cost(load_kw, fuel_table):
    """Litres (in hundredths) burned in one hour at this combined load.

    Finds the first level that is at least the load. Zero load costs nothing.
    """
    if load_kw == 0:
        return 0
    for level in fuel_table:
        if level["load_kw"] >= load_kw:
            return to_hundredths(level["litres_per_hour"], "litres_per_hour")
    raise ValueError(f"load of {load_kw} kW is above the generator capacity")


def outage_hours(data):
    """Indexes (0-9) of the hours when the grid is off."""
    return [h for h, on in enumerate(data["grid_available"]) if not on]


# ------------------------------------------------------- rule checker

def evaluate(data, powered):
    """Score a roster and list every rule it breaks.

    powered: {hour_index: [shop ids switched on]} for the outage hours.
    Returns {"value", "fuel_hundredths", "dark_hours", "violations"}.
    """
    shops = {s["id"]: s for s in data["shops"]}
    outages = outage_hours(data)
    budget = to_hundredths(data["fuel_budget_litres"], "fuel_budget_litres")
    max_dark = data["max_consecutive_dark"]
    violations = []
    value = 0
    fuel = 0
    on_at = {}                      # hour -> set of shop ids that are on

    for h in outages:
        if h not in powered:
            violations.append(f"hour {h}: no decision given")
            on_at[h] = set()
            continue
        ids = list(powered[h])
        unknown = [i for i in ids if i not in shops]
        if unknown:
            violations.append(f"hour {h}: unknown shop ids {unknown}")
        if len(set(ids)) != len(ids):
            violations.append(f"hour {h}: a shop is listed twice")
        on = {i for i in ids if i in shops}
        on_at[h] = on

        load = sum(shops[i]["kw"] for i in on)
        if load > data["generator_capacity_kw"]:
            violations.append(
                f"capacity: hour {h} load {load} kW is above {data['generator_capacity_kw']} kW")
        else:
            fuel += fuel_cost(load, data["fuel_table"])
        value += sum(shops[i]["value_per_slot"][h] for i in on)

    if fuel > budget:
        violations.append(f"fuel: {fuel / 100:.2f} L used, budget is {budget / 100:.2f} L")

    dark_hours = {sid: 0 for sid in shops}
    for sid, shop in shops.items():
        run = 0
        for h in range(HOURS):
            if h not in on_at:              # grid hour: everyone on, run resets
                run = 0
            elif sid in on_at[h]:
                run = 0
            else:
                run += 1
                dark_hours[sid] += 1
                if shop["type"] == "mandatory":
                    violations.append(f"mandatory: {sid} is dark in hour {h}")
                elif run == max_dark + 1:
                    violations.append(
                        f"dark run: {sid} is dark more than {max_dark} hours in a row (ending hour {h})")

    return {"value": value, "fuel_hundredths": fuel,
            "dark_hours": dark_hours, "violations": violations}
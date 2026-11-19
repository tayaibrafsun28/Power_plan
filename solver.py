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
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


# ---------------------------------------------------------- optimizer

def optimize(data):
    """Find the roster with the highest total value that breaks no rule.

    Plans the whole day at once with dynamic programming. After each hour
    the plan is summed up as a "state":
        (how long each normal shop has been dark in a row, litres used so far)
    and we keep the best value reached for every state.

    Returns {"status": "ok", "roster", "value", "fuel_hundredths"}
    or      {"status": "infeasible", "reason"}.
    """
    validate(data)
    shops = data["shops"]
    mandatory = [s for s in shops if s["type"] == "mandatory"]
    normal = [s for s in shops if s["type"] == "normal"]
    capacity = data["generator_capacity_kw"]
    table = data["fuel_table"]
    budget = to_hundredths(data["fuel_budget_litres"], "fuel_budget_litres")
    max_dark = data["max_consecutive_dark"]
    outages = outage_hours(data)
    n = len(normal)

    mandatory_ids = [s["id"] for s in mandatory]
    mandatory_kw = sum(s["kw"] for s in mandatory)

    if not outages:
        return {"status": "ok", "roster": {}, "value": 0, "fuel_hundredths": 0}

    # Quick infeasibility checks on the mandatory shops alone.
    if mandatory_kw > capacity:
        return {"status": "infeasible", "reason":
                f"capacity: mandatory shops {mandatory_ids} need {mandatory_kw} kW "
                f"but the generator carries {capacity} kW"}
    mandatory_fuel = fuel_cost(mandatory_kw, table)
    if mandatory_fuel * len(outages) > budget:
        return {"status": "infeasible", "reason":
                f"fuel: mandatory shops {mandatory_ids} alone need "
                f"{mandatory_fuel * len(outages) / 100:.2f} L over {len(outages)} outage hours "
                f"but the budget is {budget / 100:.2f} L"}

    # Precompute, for every subset ("mask") of normal shops, its kW.
    kw_of = [0] * (1 << n)
    for mask in range(1, 1 << n):
        low = (mask & -mask).bit_length() - 1
        kw_of[mask] = kw_of[mask & (mask - 1)] + normal[low]["kw"]
    room = capacity - mandatory_kw
    masks = [m for m in range(1 << n) if kw_of[m] <= room]
    fuel_of = {kw: fuel_cost(mandatory_kw + kw, table) for kw in set(kw_of[m] for m in masks)}

    # value of each mask in each outage hour
    def mask_value(mask, hour):
        return sum(normal[i]["value_per_slot"][hour] for i in range(n) if mask >> i & 1)

    base_value = {h: sum(s["value_per_slot"][h] for s in mandatory) for h in outages}

    # states: runs tuple -> {fuel: value};  history[h][(runs, fuel)] = (prev_runs, prev_fuel, mask)
    zero = (0,) * n
    states = {zero: {0: 0}}
    history = {}
    min_fuel_left = {}
    left = 0
    for h in reversed(range(HOURS)):
        min_fuel_left[h] = left            # cheapest possible fuel for hours after h
        if h in outages:
            left += mandatory_fuel

    for h in range(HOURS):
        new_states = {}
        back = {}
        if h not in outages:                # grid hour: everyone on, runs reset
            for runs, by_fuel in states.items():
                for fuel, value in by_fuel.items():
                    slot = new_states.setdefault(zero, {})
                    if value > slot.get(fuel, -1):
                        slot[fuel] = value
                        back[(zero, fuel)] = (runs, fuel, None)
        else:
            value_of = {m: base_value[h] + mask_value(m, h) for m in masks}
            for runs, by_fuel in states.items():
                must = 0
                for i in range(n):
                    if runs[i] >= max_dark:
                        must |= 1 << i
                for mask in masks:
                    if mask & must != must:
                        continue
                    cost = fuel_of[kw_of[mask]]
                    new_runs = tuple(0 if mask >> i & 1 else runs[i] + 1 for i in range(n))
                    slot = new_states.setdefault(new_runs, {})
                    for fuel, value in by_fuel.items():
                        new_fuel = fuel + cost
                        if new_fuel + min_fuel_left[h] > budget:
                            continue
                        new_value = value + value_of[mask]
                        if new_value > slot.get(new_fuel, -1):
                            slot[new_fuel] = new_value
                            back[(new_runs, new_fuel)] = (runs, fuel, mask)

        # Keep only states that are not beaten by one with the same runs,
        # less (or equal) fuel and at least as much value.
        pruned = {}
        for runs, by_fuel in new_states.items():
            best = -1
            keep = {}
            for fuel in sorted(by_fuel):
                if by_fuel[fuel] > best:
                    best = by_fuel[fuel]
                    keep[fuel] = best
            if keep:
                pruned[runs] = keep
        states = pruned
        history[h] = back
        if not states:
            return {"status": "infeasible", "reason":
                    f"no roster satisfies capacity ({capacity} kW), fuel ({budget / 100:.2f} L), "
                    f"mandatory shops and the {max_dark}-hour dark limit together "
                    f"(stuck at {10 + h}:00)"}

    # Best final state: highest value, then least fuel.
    best_key, best_value = None, -1
    for runs, by_fuel in states.items():
        for fuel, value in by_fuel.items():
            if value > best_value or (value == best_value and fuel < best_key[1]):
                best_key, best_value = (runs, fuel), value

    # Walk back to rebuild the roster.
    roster = {}
    key = best_key
    for h in reversed(range(HOURS)):
        prev_runs, prev_fuel, mask = history[h][key]
        if mask is not None:
            roster[h] = mandatory_ids + [normal[i]["id"] for i in range(n) if mask >> i & 1]
        key = (prev_runs, prev_fuel)
    roster = dict(sorted(roster.items()))
    return {"status": "ok", "roster": roster, "value": best_value,
            "fuel_hundredths": best_key[1]}


# -------------------------------------------------------- explanations

def explain(data, roster):
    """Say why each dark shop is dark, with numbers.

    For every dark shop in every outage hour we test one thing: what would
    happen if ONLY that shop were switched on, keeping the rest of the roster?
        capacity -> the combined load would pass the generator limit
        fuel     -> the load fits, but the day's diesel would go over budget
        no_value -> nothing breaks, so the shop must be worth 0 that hour
                    (otherwise the optimizer would have switched it on)

    This explains why a shop cannot simply be added to the final plan. It does
    not explain why this plan beat every other plan.

    Returns {hour: {shop_id: {"kind": ..., "reason": text}}}.
    """
    capacity = data["generator_capacity_kw"]
    table = data["fuel_table"]
    budget = to_hundredths(data["fuel_budget_litres"], "fuel_budget_litres")
    shops = {s["id"]: s for s in data["shops"]}

    load_at = {h: sum(shops[i]["kw"] for i in on) for h, on in roster.items()}
    fuel_at = {h: fuel_cost(load_at[h], table) for h in roster}
    day_fuel = sum(fuel_at.values())

    result = {}
    for h, on in roster.items():
        clock = f"{10 + h}:00"
        load = load_at[h]
        result[h] = {}
        for sid, shop in shops.items():
            if sid in on:
                continue
            new_load = load + shop["kw"]
            if new_load > capacity:
                kind = "capacity"
                reason = (f"Capacity: {sid} needs {shop['kw']} kW; the {load} kW already on at "
                          f"{clock} would become {new_load} kW, above the generator's {capacity} kW.")
            else:
                new_hour_fuel = fuel_cost(new_load, table)
                new_day_fuel = day_fuel - fuel_at[h] + new_hour_fuel
                if new_day_fuel > budget:
                    kind = "fuel"
                    reason = (f"Fuel: switching on {sid} ({shop['kw']} kW) lifts {clock} from "
                              f"{load} kW / {fuel_at[h] / 100:.2f} L to {new_load} kW / "
                              f"{new_hour_fuel / 100:.2f} L, taking the day to "
                              f"{new_day_fuel / 100:.2f} L against a {budget / 100:.2f} L budget.")
                else:
                    kind = "no_value"
                    reason = (f"No gain: {sid} is worth {shop['value_per_slot'][h]} at {clock}, "
                              f"so powering it would not improve the plan.")
            result[h][sid] = {"kind": kind, "reason": reason}
    return result
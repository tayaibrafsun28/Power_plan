# Power_plan

A load-shedding roster planner. Given a day's outage schedule, a generator
with limited capacity and a fixed diesel budget, it decides which shops are
powered in each outage hour, and explains why every dark shop is dark.

## Background

The problem comes from a hackathon I took part in on 12 October 2026, where
my team finished as 1st runner-up. This repository is a fresh, independent
rebuild of the idea, with my own design decisions.

## The problem in short

- One generator with a kW capacity limit and a diesel budget.
- Fuel is burned per hour based on the **combined** load, not per shop.
- Mandatory shops (pharmacy, ATM) stay on every outage hour.
- No normal shop may stay dark more than `max_consecutive_dark` hours in a row.
- Within those rules, maximise total value served.

## Planned structure

```
app.py      HTTP server (POST /api/roster + the web screen)
solver/     validation, fuel, rule checker, optimizer, explanations
web/        roster board and print view
tests/      unit tests
data/       sample inputs and outputs
evidence/   cases that broke an earlier version, and boundary checks
docs/       plan and decision log
```

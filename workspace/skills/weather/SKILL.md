---
name: weather
description: Current weather and short forecasts via wttr.in (curl). No API key. Use when the user asks about weather, temperature, or forecast for a place. Not for historical data or official severe alerts.
invocation: /weather
---

# Weather

Query **wttr.in** with `bash` + `curl`. Substitute the location (`City` or `City+Name`) for the user's place or airport code.

## Quick commands

```bash
# One-line summary
curl -s "wttr.in/London?format=3"

# Current conditions (block)
curl -s "wttr.in/London?0"

# ~3-day view
curl -s "wttr.in/London"

# JSON (for parsing)
curl -s "wttr.in/London?format=j1"
```

Custom one-liner example: `curl -s "wttr.in/Paris?format=%l:+%c+%t+%w"`

## Notes

- Free service—avoid rapid repeated requests.
- Works globally; airport codes OK (e.g. `wttr.in/PEK`).

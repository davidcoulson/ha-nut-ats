# NUT integration with ATS input sensors

The Home Assistant core `nut` integration (from HA 2026.10.1) with the changes from
[home-assistant/core#186565](https://github.com/home-assistant/core/pull/186565), packaged for HACS so it can be tested
before the PR is merged.

It adds sensors for automatic transfer switches (for example the APC AP4452A through NUT's `snmp-ups` `apc_ats` MIB):

- **Input source** (`input.source`) and **Preferred input source** (`input.source.preferred`)
- **Input N voltage** and **Input N frequency** for each `input.N.voltage` / `input.N.frequency` the device reports

Installing it replaces the built-in NUT integration; existing NUT config entries keep working. Remove it from HACS (and
restart) once the PR ships in a Home Assistant release.

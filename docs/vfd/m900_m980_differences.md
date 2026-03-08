# M900 / M980 differences

## Summary

M900 і M980 достатньо близькі для спільної архітектури transport/state model,
але не настільки однакові, щоб тримати один жорстко зашитий профіль.

## Important differences

### M980
- high protection product line
- менший/простішій IO profile
- урізаніші communication / pump-specific можливості
- max frequency typically lower

### M900
- багатший feature set
- більше pump/network-oriented режимів
- ширший набір параметрів

## Engineering rule

В коді тримати:
- один shared Modbus transport
- один shared state model
- окремі capability/profile описи

Не хардкодити в загальну логіку:
- IO count
- max frequency ceiling
- availability of advanced pump/network features
- terminal map assumptions beyond validated common subset

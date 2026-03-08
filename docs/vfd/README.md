# VFD docs index

Ця папка — базова точка правди по VFD (M900/M980) для DrukMix.

## Коли що читати

### 1. `m900_m980_shared_semantics.md`
Читати коли:
- міняєш логіку `pump_vfd` драйвера
- міняєш reset fault / stop / run семантику
- міняєш інтерпретацію status register'ів
- міняєш host/bridge/agent логіку, яка залежить від значення `fault`, `running`, `actual freq`

### 2. `m900_m980_differences.md`
Читати коли:
- додаєш підтримку конкретної серії VFD
- хочеш використати специфічні фічі M900 або M980
- міняєш IO map / capability profile / max frequency / terminal assumptions

### 3. `m900_m980_faults.md`
Читати коли:
- в терміналі Klipper або pump node прилітає код помилки
- вирішуєш, що можна скидати автоматично, а що має паузити друк
- документуєш fault policy

### 4. `modbus_driver_contract.md`
Читати коли:
- міняєш архітектуру між `agent`, `bridge`, `pump_vfd`
- міняєш state model
- додаєш нові поля статусу або профілі VFD

### 5. `config/vfd_profiles.yaml`
Читати коли:
- додаєш/правиш series profile
- хочеш винести відмінності M900/M980 з коду в конфіг

## Поточні правила проєкту

1. Один transport / status model для M900 і M980.
2. Відмінності між серіями тримати в profile/capabilities, а не розмазувати по коду.
3. `running` не вважати доказом фактичного обертання.
4. Для автоматичного recovery допустимий тільки communication-loss сценарій (`Err16` / link-loss class).
5. Усі інші fault-и мають залишатися fault-ами оператора до окремо описаної політики.

## Пов'язані вузли коду

- `firmware/pump_vfd/`
- `firmware/bridge/`
- `agent/`
- `README.md`

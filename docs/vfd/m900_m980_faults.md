# M900 / M980 baseline fault map

## Навіщо цей файл

Це швидка шпаргалка для fault code, коли код прийшов у лог Klipper / driver / bridge / pump node
і потрібно швидко зрозуміти клас проблеми та policy.

## Baseline faults for DrukMix

### Err16
- Meaning: communication fault / timeout / communication path problem
- Typical cause:
  - VFD піднявся раніше за pump board
  - board перезавантажилась і втратила link
  - неправильні RS485/Modbus params
  - проблеми з кабелем
- Policy:
  - дозволено окремий auto-recovery path
  - recovery треба робити локально на ESP / pump_vfd side
  - recovery не повинен підміняти собою інші fault-и

### Err52
- Meaning: water shortage
- Policy:
  - не автоскидати
  - пауза / операторська перевірка

### Err53
- Meaning: overpressure
- Policy:
  - не автоскидати
  - пауза / операторська перевірка

## Temporary project policy

Автоматично обробляємо тільки communication-loss class.
Усі інші fault-и зберігаємо як hard fault для оператора, поки не буде окремої специфікації.

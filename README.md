# DrukMix

Moonraker agent для синхронізації насосу (ESP-NOW) з Klipper екструзією.

## Файли
- `drukmix_agent.py` → `/home/dan/drukmix_agent.py`
- `config/drukmix.cfg` → `~/printer_data/config/drukmix.cfg`
- `config/drukmix_macros.cfg` → `~/printer_data/config/drukmix_macros.cfg`
- `systemd/drukmix.service` → `/etc/systemd/system/drukmix.service`

## Встановлення (коротко)
```bash
sudo cp -f systemd/drukmix.service /etc/systemd/system/drukmix.service
cp -f config/drukmix.cfg ~/printer_data/config/drukmix.cfg
cp -f config/drukmix_macros.cfg ~/printer_data/config/drukmix_macros.cfg
cp -f drukmix_agent.py ~/drukmix_agent.py
chmod +x ~/drukmix_agent.py

sudo systemctl daemon-reload
sudo systemctl enable --now drukmix.service
sudo systemctl restart drukmix.service

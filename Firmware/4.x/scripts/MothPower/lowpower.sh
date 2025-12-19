#!/bin/bash
#enter commands to disable unneeded services

# Read WIFI_LOWPOWER setting from controls.txt
CONTROLS_FILE="/home/pi/Desktop/Mothbox/controls.txt"
WIFI_LOWPOWER="False"

if [ -f "$CONTROLS_FILE" ]; then
    WIFI_LOWPOWER=$(grep -E '^WIFI_LOWPOWER=' "$CONTROLS_FILE" | cut -d'=' -f2 | tr -d '[:space:]')
fi

# Only block Wi-Fi if WIFI_LOWPOWER is set to True
if [ "$WIFI_LOWPOWER" = "True" ]; then
    echo "$(date): WIFI_LOWPOWER=True, blocking Wi-Fi" >> /var/log/lowpower.log
    rfkill block wifi
else
    echo "$(date): WIFI_LOWPOWER=$WIFI_LOWPOWER, keeping Wi-Fi active" >> /var/log/lowpower.log
fi


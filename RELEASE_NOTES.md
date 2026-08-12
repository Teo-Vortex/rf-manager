## RF Manager 0.4.1

Home Assistant integration now supports both transmitting and physical remote press triggers through MQTT Discovery with no YAML required.

- Every saved RF action appears as a Home Assistant button entity.
- Button presses are routed through RF Manager and transmitted by Tasmota.
- Received RF activity is published to `rfmanager/event` for MQTT automations.
- Physical presses appear as device triggers in Home Assistant's automation editor.
- Entities are refreshed automatically when devices are changed or removed.

Home Assistant must use the same MQTT broker and MQTT integration discovery must be enabled.

## RF Manager 0.5.0

Home Assistant integration now supports both transmitting and physical remote press triggers through MQTT Discovery with no YAML required.

RF activity history can now be permanently deleted from the Live RF page.

MQTT connection feedback now completes correctly and Diagnostics reports whether the broker accepted or rejected each subscription.

Fixes a database persistence error that prevented valid received RF signals from appearing in Live RF.

Each learned action now has two clear Home Assistant entities: `Send <action>` transmits the RF code, while `Received <action>` records physical remote presses and their time.

- Every saved RF action appears as a Home Assistant button entity.
- Button presses are routed through RF Manager and transmitted by Tasmota.
- Received RF activity is published to `rfmanager/event` for MQTT automations.
- Physical presses appear as device triggers in Home Assistant's automation editor.
- Entities are refreshed automatically when devices are changed or removed.

Home Assistant must use the same MQTT broker and MQTT integration discovery must be enabled.

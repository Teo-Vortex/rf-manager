## RF Manager 0.1.2

This patch fixes MQTT connection handling with paho-mqtt 2.x.

- Correctly handles the MQTT v2 `ReasonCode` callback value.
- Successful broker connections can now complete normally.
- Authentication failures are shown with their real broker reason.

The application does not transmit RF or publish Home Assistant Discovery yet.

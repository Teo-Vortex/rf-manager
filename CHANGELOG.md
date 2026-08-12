# Changelog

All notable changes use Semantic Versioning.

## [0.2.1] - 2026-08-12

### Added

- Edit device and relearn individual remote buttons.
- Duplicate RF code conflict details with explicit allow-duplicate confirmation.
- Device update API with full code replacement and validation.

## [0.2.0] - 2026-08-12

### Added

- Devices page and Remote Control creation wizard.
- Configurable button count, action names and live RF learning confirmation.
- Persistent Device and RFCode database models and CRUD API.
- Known device/action matching in the Live RF monitor.

## [0.1.2] - 2026-08-12

### Fixed

- Handle paho-mqtt 2.x `ReasonCode` objects without an invalid integer conversion.
- Allow successful MQTT connections to complete and report actual broker rejection reasons.

## [0.1.1] - 2026-08-12

### Added

- Diagnostics Console with live backend and MQTT logs.
- Detailed connection attempts, DNS resolution, reconnect timing and MQTT reason codes.
- Copy, pause and clear-view controls for troubleshooting on ZimaOS.

### Security

- Diagnostics expose only whether credentials are configured; passwords are never logged.

## [0.1.0] - 2026-08-12

### Added

- Initial Docker-based Phase 1 application.
- UI-managed MQTT connection and Tasmota topic configuration.
- Live RF monitor, SQLite storage, WebSocket updates and duplicate grouping.
- Tasmota RF parser tests and Docker health check.

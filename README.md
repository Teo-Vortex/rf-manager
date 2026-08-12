# RF Manager

RF Manager is a local web application for receiving and managing 433 MHz RF signals through a Sonoff RF Bridge running Tasmota. It uses MQTT as the only primary transport and is intended to become a Zigbee2MQTT-style manager for simple RF devices.

The current release includes receiving, learning, fixed-code transmission and Home Assistant integration:

- FastAPI backend and React/TypeScript UI
- SQLite event storage in a persistent Docker volume
- MQTT connection configured entirely from the UI
- tolerant parser for Tasmota `RfReceived` messages
- live WebSocket RF monitor
- configurable 300 ms duplicate suppression
- automatic MQTT reconnect with exponential backoff
- Docker health check and GitHub-ready CI
- Home Assistant MQTT Discovery button entities and RF event topic

## Architecture

```text
433 MHz device → Sonoff RF Bridge/Tasmota → MQTT broker → RF Manager → browser
```

## Quick start with Docker

Requirements: Docker Desktop with Docker Compose.

```shell
docker compose up -d --build
```

Open <http://localhost:8765>. The MQTT connection form opens automatically when the broker is unavailable.

Enter the broker address and press **Save & connect**. Common addresses:

- Mosquitto on the same Windows/Mac computer: `host.docker.internal`
- Mosquitto on another LAN machine: its LAN IP address, for example `192.168.1.20`
- Mosquitto in the same Compose network: its Compose service name

The default subscription `tele/+/RESULT` listens to all Tasmota devices. To restrict it to one bridge, use `tele/rfbridge/RESULT`, replacing `rfbridge` with that device's Tasmota topic.

No `.env` file is required. Copy `.env.example` to `.env` only when you want deployment-time defaults or a different web port.

## Install on ZimaOS

Released versions are published as multi-architecture images to GitHub Container Registry. In ZimaOS, open the app installer and import the Compose file from `zimaos/docker-compose.yml`.

The included manifest uses the public image `ghcr.io/teo-vortex/rf-manager:latest`. After installation:

1. Open `http://ZIMAOS_IP:8765`.
2. Set the MQTT host to `host.docker.internal` because Mosquitto runs on the same ZimaOS host.
3. Keep port `1883` for standard MQTT TCP.
4. Enter the Mosquitto username and password and select **Save & connect**.

Data is kept at `/DATA/AppData/rf-manager/data` and survives image updates and container recreation.

## Publishing a release

The `VERSION` file is the version source of truth. Push a matching semantic version tag to build and publish `amd64` and `arm64` images:

```shell
git tag v0.1.0
git push origin main --tags
```

The release workflow publishes `ghcr.io/OWNER/REPOSITORY:0.1.0` and `:latest`, then creates a GitHub Release. The package must be public for password-free installation by ZimaOS.

## Tasmota configuration

In the Tasmota console, configure the MQTT broker and topic. A typical setup is:

```text
MqttHost 192.168.1.20
MqttPort 1883
Topic rfbridge
SetOption19 0
```

After Tasmota connects to the broker, an RF reception should publish a JSON payload to `tele/rfbridge/RESULT` containing `RfReceived`. RF Manager will show it immediately in **Live RF activity**.

## Home Assistant

Home Assistant and RF Manager must connect to the same MQTT broker. Keep **Enable Home Assistant MQTT Discovery** selected in RF Manager. Every saved remote action is exposed as a `Send <action>` button entity and a `Received <action>` event entity automatically; no YAML is required.

Each learned action is also exposed as an MQTT device trigger. In Home Assistant's automation editor, select the saved remote as the device and its named button press as the trigger.

Received RF signals are published as JSON to `rfmanager/event`. Use that topic in an MQTT automation trigger and optionally filter fields such as `device_name`, `action`, or `code`.

To verify the MQTT traffic independently:

```shell
mosquitto_sub -h BROKER_IP -t "tele/+/RESULT" -v
```

## Data and backup

Persistent data is stored in `./data/rfmanager.db`. Stop the container before directly copying the SQLite file for a simple consistent backup:

```shell
docker compose stop
```

Copy `data/rfmanager.db`, then start again with `docker compose start`.

MQTT credentials saved through the UI are stored locally in this database and are never returned by the API or logged. Keep the project directory and database accessible only to trusted users.

## Development checks

```shell
docker build --target frontend-build .
docker compose build
docker compose run --rm rf-manager pytest
```

## Planned phases

1. Device CRUD, learning wizard and mappings
2. Tasmota RF transmission
3. Home Assistant MQTT Discovery
4. Additional sensor types
5. GitHub release checking and safe, user-triggered Docker/ZimaOS update workflow

The update workflow will preserve `/data` and will not require unrestricted Docker socket access by default.

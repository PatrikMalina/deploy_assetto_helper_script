# Assetto Corsa Server Deployment

This project replaces the large `deploy\_assetto` Bash script with a small Bash launcher and modular Python code.

It manages:

* Assetto Corsa server deployment
* automatic backup and rollback
* `acbop` UDP plugin configuration
* persistent Content Manager configuration
* Content Manager car and track download URLs
* `assetto`, `assetto-content`, and `acbop` systemd services
* package discovery for ZIP, 7Z, and RAR files

## Files

```text
/opt/assetto-deploy/
├── config.json
├── deploy.py
├── content_manager.py
└── utils.py

/usr/local/bin/deploy_assetto
```

## Installation

Create the application directory:

```bash
sudo mkdir -p /opt/assetto-deploy
```

Copy these files into it:

```text
config.json
deploy.py
content_manager.py
utils.py
```

Install the launcher:

```bash
sudo cp deploy\_assetto /usr/local/bin/deploy_assetto
sudo chmod 755 /usr/local/bin/deploy_assetto
```

Make the Python script executable:

```bash
sudo chmod 755 /opt/assetto-deploy/deploy.py
```

Check Python syntax:

```bash
sudo python3 -m py\_compile \\
  /opt/assetto-deploy/deploy.py \\
  /opt/assetto-deploy/content_manager.py \\
  /opt/assetto-deploy/utils.py
```

No output means the syntax check passed.

## Configuration

All installation specific settings are stored in:

```text
/opt/assetto-deploy/config.json
```

The default configuration included with this project is:

```json
{
  "upload_dir": "/opt/assetto/upload",
  "server_dir": "/opt/assetto/assetto",
  "shared_dir": "/opt/assetto/assetto_shared",
  "temp_dir": "/tmp/assetto_deploy",
  "backup_dir": "/tmp/assetto_backup",
  "content_backup": "/tmp/assetto_content.json.backup",
  "assetto_service": "assetto",
  "content_service": "assetto-content",
  "bop_service": "acbop",
  "assetto_user": "assetto",
  "assetto_group": "assetto",
  "udp_plugin_address": "127.0.0.1:12000",
  "udp_plugin_local_port": "11000",
  "content_base_url": "http://IP:8051"
}
```

## HTTP and HTTPS download URLs

The Content Manager URL is controlled by one setting:

```json
"content_base_url": "http://1IP:8051"
```

For the current direct HTTP setup, leave it as above.

If HTTPS is added later through a reverse proxy, only change this value, for example:

```json
"content_base_url": "https://content.example.com"
```

No Python code needs to be changed.

## Package directories

Car packages:

```text
/opt/assetto/assetto_shared/packages/cars
```

Track packages:

```text
/opt/assetto/assetto_shared/packages/tracks
```

Supported package formats:

```text
.zip
.7z
.rar
```

## Package naming

The package may optionally begin with `car-` or `track-`.

The Assetto content ID must follow that optional prefix.

Additional text, version information, or package version suffixes may follow the ID.

Examples for car ID:

```text
R3_Suzuki_Swift
```

Valid package names include:

```text
R3_Suzuki_Swift.zip
car-R3_Suzuki_Swift.zip
car-R3_Suzuki_Swift-1.0.zip
car-R3_Suzuki_Swift-Rally R3 by GR.TEAM 1.0-2.zip
```

Examples for track ID:

```text
rt_california_highway
```

Valid package names include:

```text
rt_california_highway.7z
track-rt_california_highway.7z
track-rt_california_highway-1.1.7z
```

If several files match the same content ID, the newest file by modification time is used.

## Content Manager JSON

The generated file is:

```text
/opt/assetto/assetto_shared/cm_content/content.json
```

It is rebuilt from scratch on every successful deployment.

Only cars and the track used by the newly deployed server are written into it.

For example:

```json
{
  "cars": {
    "R3_Suzuki_Swift": {
      "url": "http://146.59.105.73:8051/cars/car-R3_Suzuki_Swift-Rally%20R3%20by%20GR.TEAM%201.0-2.zip"
    }
  },
  "track": {
    "url": "http://146.59.105.73:8051/tracks/track-chq_sepang.zip"
  }
}
```

Spaces and other unsafe URL characters in filenames are automatically URL encoded.

Packages not used by the current server remain on disk but are not included in `content.json`.

## Missing packages

Missing packages do not abort deployment.

The script prints a warning such as:

```text
WARNING: No download package found for car: mercedes_sls_gt3
WARNING: No download package found for track: ks_silverstone
```

At the end of Content Manager generation it also prints a summary of found and missing packages.

## acbop

Every deployment automatically configures these settings inside the `\[SERVER]` section of:

```text
/opt/assetto/assetto/cfg/server_cfg.ini
```

Values:

```ini
UDP_PLUGIN_ADDRESS=127.0.0.1:12000
UDP_PLUGIN_LOCAL_PORT=11000
```

If the lines already exist, they are replaced.

If they are missing, they are inserted into `\[SERVER]`.

The deployment also creates:

```text
/opt/assetto/assetto/results
```

This is required for correct lap event handling by acbop.

## Services

The deployment manages:

```text
assetto.service
assetto-content.service
acbop.service
```

Deployment order:

```text
stop assetto
stop acbop
stop assetto-content

install new server
configure acbop
build content.json

start assetto-content
start acbop
start assetto
```

The Assetto service is checked after startup.

If deployment fails after the live server has been changed, the previous server and previous `content.json` are restored automatically.

## Running a deployment

Usage remains unchanged:

```bash
sudo deploy_assetto /opt/assetto/upload/server.tar.gz
```

The launcher passes the archive name to the Python deployment application.

## Useful checks

Check generated Content Manager configuration:

```bash
cat /opt/assetto/assetto_shared/cm_content/content.json
```

Check acbop configuration:

```bash
grep -E '^UDP_PLUGIN_' \\
  /opt/assetto/assetto/cfg/server_cfg.ini
```

Check all services:

```bash
systemctl status \\
  assetto \\
  assetto-content \\
  acbop \\
  --no-pager
```

Check the content server:

```bash
curl http://127.0.0.1:8051/
```

Check one generated package URL directly from another computer before relying on Content Manager.

## Changing to HTTPS later

When a reverse proxy is configured in front of the content server, edit:

```text
/opt/assetto-deploy/config.json
```

Change only:

```json
"content_base_url": "https://content.example.com"
```

The rest of the deployment system does not need to change.


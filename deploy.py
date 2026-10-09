#!/usr/bin/env python3

import json
import os
import shutil
import sys
import tarfile
import time
import zipfile
from pathlib import Path

from content_manager import (
    import_packaged_content,
    update_content_manager,
)
from utils import (
    chown_recursive,
    clear_directory,
    copy_directory_contents,
    log,
    remove_path,
    service_active,
    service_restart,
    service_start,
    service_stop,
    show_logs,
)


BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"


def load_config():
    with CONFIG_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


CONFIG = load_config()

UPLOAD_DIR = Path(CONFIG["upload_dir"])
SERVER_DIR = Path(CONFIG["server_dir"])
SHARED_DIR = Path(CONFIG["shared_dir"])
TEMP_DIR = Path(CONFIG["temp_dir"])
BACKUP_DIR = Path(CONFIG["backup_dir"])
CONTENT_BACKUP = Path(CONFIG["content_backup"])

CM_DIR = SHARED_DIR / "cm_content"
CONTENT_JSON = CM_DIR / "content.json"
CAR_PACKAGES = SHARED_DIR / "packages" / "cars"
TRACK_PACKAGES = SHARED_DIR / "packages" / "tracks"

ASSETTO_SERVICE = CONFIG["assetto_service"]
CONTENT_SERVICE = CONFIG["content_service"]
BOP_SERVICE = CONFIG["bop_service"]

ASSETTO_USER = CONFIG["assetto_user"]
ASSETTO_GROUP = CONFIG["assetto_group"]

UDP_PLUGIN_ADDRESS = CONFIG["udp_plugin_address"]
UDP_PLUGIN_LOCAL_PORT = str(CONFIG["udp_plugin_local_port"])

CONTENT_BASE_URL = CONFIG["content_base_url"]


def extract_archive(archive, destination):
    clear_directory(destination)

    name = archive.name.lower()

    log("Extracting package...")

    if name.endswith(".tar.gz") or name.endswith(".tgz"):
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(destination)
    elif name.endswith(".tar"):
        with tarfile.open(archive, "r:") as tar:
            tar.extractall(destination)
    elif name.endswith(".zip"):
        with zipfile.ZipFile(archive, "r") as z:
            z.extractall(destination)
    else:
        raise RuntimeError(
            "Unsupported archive format. Supported: tar.gz, tgz, tar, zip"
        )


def validate_package():
    ac_server = TEMP_DIR / "acServer"
    server_cfg = TEMP_DIR / "cfg" / "server_cfg.ini"

    if not ac_server.is_file():
        raise RuntimeError(
            "acServer was not found in the package."
        )

    if not server_cfg.is_file():
        raise RuntimeError(
            "cfg/server_cfg.ini was not found in the package."
        )

    log("Package looks valid.")


def update_server_section_value(lines, key, value):
    section_start = None
    section_end = len(lines)

    for index, line in enumerate(lines):
        stripped = line.strip()

        if stripped.upper() == "[SERVER]":
            section_start = index

            for next_index in range(index + 1, len(lines)):
                candidate = lines[next_index].strip()

                if candidate.startswith("[") and candidate.endswith("]"):
                    section_end = next_index
                    break

            break

    if section_start is None:
        raise RuntimeError(
            "[SERVER] section not found in server_cfg.ini"
        )

    prefix = f"{key}="

    for index in range(section_start + 1, section_end):
        if lines[index].strip().startswith(prefix):
            lines[index] = f"{key}={value}\n"
            return lines

    lines.insert(
        section_end,
        f"{key}={value}\n",
    )

    return lines


def configure_udp_plugin(server_cfg):
    log("Configuring ac-bop UDP plugin...")

    lines = Path(server_cfg).read_text(
        encoding="utf-8",
        errors="replace",
    ).splitlines(keepends=True)

    lines = update_server_section_value(
        lines,
        "UDP_PLUGIN_ADDRESS",
        UDP_PLUGIN_ADDRESS,
    )

    lines = update_server_section_value(
        lines,
        "UDP_PLUGIN_LOCAL_PORT",
        UDP_PLUGIN_LOCAL_PORT,
    )

    Path(server_cfg).write_text(
        "".join(lines),
        encoding="utf-8",
    )

    log(
        f"UDP_PLUGIN_ADDRESS={UDP_PLUGIN_ADDRESS}"
    )
    log(
        f"UDP_PLUGIN_LOCAL_PORT={UDP_PLUGIN_LOCAL_PORT}"
    )


def prepare_shared_directories():
    log("Preparing shared directories...")

    CM_DIR.mkdir(parents=True, exist_ok=True)
    CAR_PACKAGES.mkdir(parents=True, exist_ok=True)
    TRACK_PACKAGES.mkdir(parents=True, exist_ok=True)

    if not CONTENT_JSON.exists():
        CONTENT_JSON.write_text(
            json.dumps(
                {
                    "cars": {},
                    "track": {},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    chown_recursive(
        SHARED_DIR,
        ASSETTO_USER,
        ASSETTO_GROUP,
    )


def backup_existing_server():
    log("Creating server backup...")

    remove_path(BACKUP_DIR)
    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if SERVER_DIR.is_dir():
        copy_directory_contents(
            SERVER_DIR,
            BACKUP_DIR,
        )


def backup_content_json():
    CONTENT_BACKUP.unlink(
        missing_ok=True
    )

    if CONTENT_JSON.is_file():
        shutil.copy2(
            CONTENT_JSON,
            CONTENT_BACKUP,
        )


def restore_content_json():
    if CONTENT_BACKUP.is_file():
        log("Restoring content.json...")

        shutil.copy2(
            CONTENT_BACKUP,
            CONTENT_JSON,
        )

        chown_recursive(
            CONTENT_JSON,
            ASSETTO_USER,
            ASSETTO_GROUP,
        )

        CONTENT_JSON.chmod(0o644)


def install_server():
    log("Removing old server files...")
    clear_directory(SERVER_DIR)

    log("Installing new server...")
    copy_directory_contents(
        TEMP_DIR,
        SERVER_DIR,
    )

    source_cm_dir = (
        SERVER_DIR
        / "cfg"
        / "cm_content"
    )
    
    import_packaged_content(
        source_cm_dir=source_cm_dir,
        car_packages=CAR_PACKAGES,
        track_packages=TRACK_PACKAGES,
        assetto_user=ASSETTO_USER,
        assetto_group=ASSETTO_GROUP,
    )

    server_cfg = (
        SERVER_DIR
        / "cfg"
        / "server_cfg.ini"
    )

    configure_udp_plugin(server_cfg)

    log(
        "Linking persistent Content Manager configuration..."
    )

    cfg_dir = SERVER_DIR / "cfg"
    cfg_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    cm_link = cfg_dir / "cm_content"
    remove_path(cm_link)
    cm_link.symlink_to(CM_DIR)

    ac_server = SERVER_DIR / "acServer"
    ac_server.chmod(
        ac_server.stat().st_mode | 0o111
    )

    chown_recursive(
        SERVER_DIR,
        ASSETTO_USER,
        ASSETTO_GROUP,
    )

    chown_recursive(
        SHARED_DIR,
        ASSETTO_USER,
        ASSETTO_GROUP,
    )

    return server_cfg


def start_and_verify_services():
    log("")
    service_start(CONTENT_SERVICE)

    if not service_active(CONTENT_SERVICE):
        show_logs(CONTENT_SERVICE)
        raise RuntimeError(
            "Content download server failed to start"
        )

    service_start(BOP_SERVICE)

    if not service_active(BOP_SERVICE):
        show_logs(BOP_SERVICE)
        raise RuntimeError(
            "acbop failed to start"
        )

    service_start(ASSETTO_SERVICE)

    time.sleep(3)

    if not service_active(ASSETTO_SERVICE):
        show_logs(ASSETTO_SERVICE)
        raise RuntimeError(
            "Assetto Corsa failed to start"
        )


def rollback():
    log("")
    log("========================================")
    log(" Rolling back deployment")
    log("========================================")
    log("")

    service_stop(ASSETTO_SERVICE)
    service_stop(BOP_SERVICE)

    clear_directory(SERVER_DIR)

    if BACKUP_DIR.is_dir():
        copy_directory_contents(
            BACKUP_DIR,
            SERVER_DIR,
        )

    restore_content_json()

    if SERVER_DIR.exists():
        chown_recursive(
            SERVER_DIR,
            ASSETTO_USER,
            ASSETTO_GROUP,
        )

    if SHARED_DIR.exists():
        chown_recursive(
            SHARED_DIR,
            ASSETTO_USER,
            ASSETTO_GROUP,
        )

    ac_server = SERVER_DIR / "acServer"

    if ac_server.is_file():
        ac_server.chmod(
            ac_server.stat().st_mode | 0o111
        )

    service_restart(CONTENT_SERVICE)

    try:
        service_start(BOP_SERVICE)
    except Exception:
        log("WARNING: acbop failed to restart.")

    try:
        service_start(ASSETTO_SERVICE)
    except Exception:
        log("WARNING: Assetto failed to restart.")

    log("")
    log("Previous server restored.")
    log("")
    log("Recent Assetto logs:")
    log("")
    show_logs(
        ASSETTO_SERVICE,
        30,
    )


def cleanup(success, archive=None):
    remove_path(TEMP_DIR)
    remove_path(BACKUP_DIR)

    CONTENT_BACKUP.unlink(
        missing_ok=True
    )

    if success and archive:
        Path(archive).unlink(
            missing_ok=True
        )


def main():
    if os.geteuid() != 0:
        log(
            "ERROR: deploy_assetto must be run as root."
        )
        return 1

    if len(sys.argv) != 2:
        log("Usage:")
        log(
            "sudo deploy_assetto filename.tar.gz"
        )
        return 1

    archive_name = Path(
        sys.argv[1]
    ).name

    archive = (
        UPLOAD_DIR
        / archive_name
    )

    if not archive.is_file():
        log("")
        log("ERROR: File not found:")
        log(str(archive))
        log("")
        return 1

    log("")
    log("========================================")
    log(" Assetto Corsa deployment")
    log("========================================")
    log("")
    log(
        f"Package: {archive_name}"
    )
    log("")

    changed_running_server = False

    try:
        prepare_shared_directories()

        extract_archive(
            archive,
            TEMP_DIR,
        )

        validate_package()

        backup_content_json()
        backup_existing_server()

        log("")
        service_stop(ASSETTO_SERVICE)
        service_stop(BOP_SERVICE)
        service_stop(CONTENT_SERVICE)

        changed_running_server = True

        server_cfg = install_server()

        update_content_manager(
            server_cfg=server_cfg,
            content_json=CONTENT_JSON,
            car_packages=CAR_PACKAGES,
            track_packages=TRACK_PACKAGES,
            content_base_url=CONTENT_BASE_URL,
            assetto_user=ASSETTO_USER,
            assetto_group=ASSETTO_GROUP,
        )

        start_and_verify_services()

        cleanup(
            success=True,
            archive=archive,
        )

        log("")
        log("========================================")
        log(" Deployment successful")
        log("========================================")
        log("")
        log("Assetto Corsa: running")
        log("ac-bop: running")
        log("Content server: running")
        log("")
        log(
            "UDP plugin: "
            f"{UDP_PLUGIN_ADDRESS}"
        )
        log(
            "UDP local port: "
            f"{UDP_PLUGIN_LOCAL_PORT}"
        )
        log(
            "Content base URL: "
            f"{CONTENT_BASE_URL}"
        )
        log("")

        return 0

    except Exception as error:
        log("")
        log("========================================")
        log(" Deployment failed")
        log("========================================")
        log("")
        log(f"ERROR: {error}")
        log("")

        if changed_running_server:
            try:
                rollback()
            except Exception as rollback_error:
                log("")
                log(
                    "CRITICAL: rollback also failed:"
                )
                log(
                    str(rollback_error)
                )
        else:
            log(
                "Running server was not modified."
            )

        cleanup(
            success=False
        )

        return 1


if __name__ == "__main__":
    sys.exit(main())

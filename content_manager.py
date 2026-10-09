#!/usr/bin/env python3

import json
from pathlib import Path
from urllib.parse import quote

from utils import chown_recursive, log


SUPPORTED_PACKAGE_EXTENSIONS = (
    ".zip",
    ".7z",
    ".rar",
)


def read_cfg_value(server_cfg, key):
    prefix = f"{key}="

    with Path(server_cfg).open(
        "r",
        encoding="utf-8",
        errors="replace",
    ) as file:
        for line in file:
            stripped = line.strip()

            if stripped.startswith(prefix):
                return stripped.split("=", 1)[1].strip()

    return ""


def package_stem(filename):
    lower = filename.lower()

    for extension in SUPPORTED_PACKAGE_EXTENSIONS:
        if lower.endswith(extension):
            return filename[:-len(extension)]

    return None


def find_package(directory, content_id, package_type):
    """
    Supported examples:

    R3_Suzuki_Swift.zip
    car-R3_Suzuki_Swift.zip
    car-R3_Suzuki_Swift-1.0.zip
    car-R3_Suzuki_Swift-Rally R3 by GR.TEAM 1.0-2.zip

    ks_silverstone.7z
    track-ks_silverstone.rar
    track-ks_silverstone-1.1.zip

    If multiple matching files exist, the newest file is selected.
    """

    directory = Path(directory)
    prefix = f"{package_type}-"
    matches = []

    if not directory.is_dir():
        return None

    for path in directory.iterdir():
        if not path.is_file():
            continue

        stem = package_stem(path.name)

        if stem is None:
            continue

        candidate = stem

        if candidate.lower().startswith(prefix.lower()):
            candidate = candidate[len(prefix):]

        candidate_lower = candidate.lower()
        id_lower = content_id.lower()

        if candidate_lower == id_lower:
            matches.append(path)
            continue

        if candidate_lower.startswith(id_lower + "-"):
            matches.append(path)
            continue

        if candidate_lower.startswith(id_lower + " "):
            matches.append(path)

    if not matches:
        return None

    matches.sort(
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if len(matches) > 1:
        log(
            f"Multiple packages found for {content_id}; "
            f"using newest: {matches[0].name}"
        )

    return matches[0]


def package_url(package, package_type, content_base_url):
    filename = quote(
        package.name,
        safe="",
    )

    return (
        f"{content_base_url.rstrip('/')}/"
        f"{package_type}s/"
        f"{filename}"
    )


def update_content_manager(
    server_cfg,
    content_json,
    car_packages,
    track_packages,
    content_base_url,
    assetto_user,
    assetto_group,
):
    """
    Rebuild content.json from scratch using only the cars and track
    from the newly deployed server.
    """

    log("")
    log("Updating Content Manager downloads...")

    cars_raw = read_cfg_value(
        server_cfg,
        "CARS",
    )

    track = read_cfg_value(
        server_cfg,
        "TRACK",
    ).strip()

    data = {
        "cars": {},
        "track": {},
    }

    missing_cars = []
    missing_track = None

    cars = [
        car.strip()
        for car in cars_raw.split(";")
        if car.strip()
    ]

    for car in cars:
        package = find_package(
            car_packages,
            car,
            "car",
        )

        if package is None:
            log(
                f"WARNING: No download package found for car: {car}"
            )
            missing_cars.append(car)
            continue

        url = package_url(
            package,
            "car",
            content_base_url,
        )

        log(f"Car: {car}")
        log(f"  Package: {package.name}")
        log(f"  URL: {url}")

        data["cars"][car] = {
            "url": url
        }

    if track:
        package = find_package(
            track_packages,
            track,
            "track",
        )

        if package is None:
            log(
                f"WARNING: No download package found for track: {track}"
            )
            missing_track = track
        else:
            url = package_url(
                package,
                "track",
                content_base_url,
            )

            log(f"Track: {track}")
            log(f"  Package: {package.name}")
            log(f"  URL: {url}")

            data["track"] = {
                "url": url
            }

    content_json = Path(content_json)
    temporary_json = content_json.with_suffix(".json.tmp")

    temporary_json.write_text(
        json.dumps(
            data,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary_json.replace(content_json)

    chown_recursive(
        content_json,
        assetto_user,
        assetto_group,
    )

    content_json.chmod(0o644)

    log("")
    log("New Content Manager configuration:")
    log(
        json.dumps(
            data,
            indent=2,
        )
    )

    log("")
    log("Content package summary:")
    log(f"  Cars configured: {len(cars)}")
    log(f"  Car packages found: {len(data['cars'])}")
    log(f"  Car packages missing: {len(missing_cars)}")

    if track:
        log(
            "  Track package: "
            + ("missing" if missing_track else "found")
        )
    else:
        log("  Track package: no track configured")

    if missing_cars:
        log("")
        log("Missing car packages:")
        for car in missing_cars:
            log(f"  {car}")

    if missing_track:
        log("")
        log("Missing track package:")
        log(f"  {missing_track}")

    return {
        "missing_cars": missing_cars,
        "missing_track": missing_track,
    }

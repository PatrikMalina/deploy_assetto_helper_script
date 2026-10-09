#!/usr/bin/env python3

import os
import pwd
import grp
import shutil
import subprocess
from pathlib import Path


def log(message=""):
    print(message, flush=True)


def run(command, check=True, capture=False):
    command = [str(x) for x in command]
    log(f"  > {' '.join(command)}")
    return subprocess.run(
        command,
        check=check,
        text=True,
        capture_output=capture,
    )


def service_start(service):
    log(f"Starting {service}...")
    run(["systemctl", "start", service])


def service_stop(service):
    log(f"Stopping {service}...")
    subprocess.run(
        ["systemctl", "stop", service],
        check=False,
    )


def service_restart(service):
    log(f"Restarting {service}...")
    subprocess.run(
        ["systemctl", "restart", service],
        check=False,
    )


def service_active(service):
    result = subprocess.run(
        ["systemctl", "is-active", "--quiet", service],
        check=False,
    )
    return result.returncode == 0


def show_logs(service, lines=30):
    subprocess.run(
        [
            "journalctl",
            "-u",
            service,
            "-n",
            str(lines),
            "--no-pager",
        ],
        check=False,
    )


def remove_path(path):
    path = Path(path)

    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def clear_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    for child in path.iterdir():
        remove_path(child)


def copy_directory_contents(source, destination):
    source = Path(source)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    for child in source.iterdir():
        target = destination / child.name

        if child.is_symlink():
            target.symlink_to(os.readlink(child))
        elif child.is_dir():
            shutil.copytree(child, target, symlinks=True)
        else:
            shutil.copy2(child, target)


def chown_recursive(path, user, group):
    path = Path(path)

    if not path.exists() and not path.is_symlink():
        return

    uid = pwd.getpwnam(user).pw_uid
    gid = grp.getgrnam(group).gr_gid

    if path.is_symlink():
        os.lchown(path, uid, gid)
        return

    os.chown(path, uid, gid)

    if not path.is_dir():
        return

    for root, dirs, files in os.walk(path, followlinks=False):
        root_path = Path(root)

        for name in dirs:
            item = root_path / name
            if item.is_symlink():
                os.lchown(item, uid, gid)
            else:
                os.chown(item, uid, gid)

        for name in files:
            item = root_path / name
            if item.is_symlink():
                os.lchown(item, uid, gid)
            else:
                os.chown(item, uid, gid)

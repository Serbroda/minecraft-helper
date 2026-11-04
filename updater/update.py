#!/usr/bin/env python3
"""Dependency-free Minecraft file updater. Requires Python 3.9+."""

import argparse
import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen
import zipfile
import truststore

truststore.inject_into_ssl()


# Limits apply to each download and to the total extracted content of each ZIP.
MAX_BYTES = 2 * 1024 * 1024 * 1024
MAX_ENTRIES = 20000
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    prefix + str(i) for prefix in ("COM", "LPT") for i in range(1, 10)
}


class UpdateError(Exception):
    pass


def relative_path(value):
    """Reject traversal and names that are unsafe on either supported OS."""
    if not isinstance(value, str) or not value or "\\" in value:
        raise UpdateError(f"Ungültiger relativer Dateipfad: {value!r}")
    parts = value.split("/")
    for part in parts:
        if (not part or part in (".", "..") or part.endswith((" ", "."))
                or re.search(r'[<>:"|?*\x00-\x1f]', part)
                or part.split(".")[0].upper() in RESERVED):
            raise UpdateError(f"Unsicherer Dateipfad: {value!r}")
    return Path(*parts)


def configured_path(value, base):
    if not isinstance(value, str) or not value.strip():
        raise UpdateError("Ein Pfad muss eine nicht leere Zeichenkette sein.")
    result = Path(os.path.expandvars(os.path.expanduser(value)))
    return result if result.is_absolute() else base / result


def load_config(path):
    with path.open(encoding="utf-8-sig") as handle:
        config = json.load(handle)
    if not isinstance(config, dict) or not isinstance(config.get("targets"), list):
        raise UpdateError("Die Konfiguration benötigt eine Liste 'targets'.")
    if not config["targets"]:
        raise UpdateError("Es ist kein Ziel konfiguriert.")
    return config


def copy_limited(source, destination, limit=MAX_BYTES):
    total = 0
    while True:
        chunk = source.read(1024 * 1024)
        if not chunk:
            return total
        total += len(chunk)
        if total > limit:
            raise UpdateError("Größenlimit überschritten (max. 2 GiB pro Quelle/ZIP).")
        destination.write(chunk)


def download(url, destination):
    if not isinstance(url, str) or urlsplit(url).scheme not in ("https", "http"):
        raise UpdateError("Downloads benötigen eine HTTP- oder HTTPS-URL.")
    request = Request(url, headers={"User-Agent": "MinecraftFileUpdater/1.0"})
    # urllib validates TLS certificates by default; never disable that check.
    with urlopen(request, timeout=60) as response, destination.open("wb") as output:
        if urlsplit(response.geturl()).scheme not in ("https", "http"):
            raise UpdateError("Weiterleitung auf ein unzulässiges Protokoll.")
        copy_limited(response, output)


def ensure_safe_destination(destination):
    # Do not resolve(): that would hide symbolic links before we inspect them.
    for component in (destination, *destination.parents):
        try:
            attributes = getattr(component.lstat(), "st_file_attributes", 0)
        except FileNotFoundError:
            attributes = 0
        # Windows reparse points include junctions (also on Python < 3.12).
        if component.is_symlink() or attributes & 0x400:
            raise UpdateError(f"Symlink/Junction als Ziel nicht erlaubt: {component}")
        if component.exists() and component != destination and not component.is_dir():
            raise UpdateError(f"Ein übergeordneter Pfad ist keine Mappe: {component}")
    if destination.exists() and not destination.is_file():
        raise UpdateError(f"Das Dateiziel ist keine reguläre Datei: {destination}")


def fingerprint(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(config, base, staging):
    """Fetch everything before touching any destination; return a change plan."""
    plan = []
    destinations = set()

    def add(source, root, relative, label):
        destination = root / relative
        key = str(destination).casefold()
        if key in destinations:
            raise UpdateError(f"Mehrfach belegtes Dateiziel: {destination}")
        destinations.add(key)
        ensure_safe_destination(destination)
        old_hash = fingerprint(destination) if destination.exists() else None
        new_hash = fingerprint(source)
        action = "GLEICH" if old_hash == new_hash else "ERSETZEN" if old_hash else "NEU"
        plan.append({"source": source, "destination": destination,
                     "old_hash": old_hash, "action": action, "label": label})

    for index, target in enumerate(config["targets"]):
        if not isinstance(target, dict):
            raise UpdateError("Jedes Ziel muss ein JSON-Objekt sein.")
        root = Path(os.path.abspath(configured_path(target.get("directory"), base)))
        label = target.get("name", f"Ziel {index + 1}")
        if ("urls" in target) == ("zip" in target):
            raise UpdateError(f"{label}: Genau eines von 'urls' und 'zip' angeben.")
        work = staging / str(index)
        work.mkdir()
        print(f"Vorbereiten: {label}", flush=True)
        if "urls" in target:
            if not isinstance(target["urls"], list) or not target["urls"]:
                raise UpdateError(f"{label}: 'urls' muss eine nicht leere Liste sein.")
            for number, entry in enumerate(target["urls"]):
                if isinstance(entry, str):
                    url, name = entry, unquote(urlsplit(entry).path.rsplit("/", 1)[-1])
                elif isinstance(entry, dict) and isinstance(entry.get("url"), str):
                    url = entry["url"]
                    name = entry.get("filename", unquote(urlsplit(url).path.rsplit("/", 1)[-1]))
                else:
                    raise UpdateError(f"{label}: Ungültiger URL-Eintrag.")
                relative = relative_path(name)
                source = work / str(number)
                download(url, source)
                add(source, root, relative, label)
        else:
            archive = target["zip"]
            if not isinstance(archive, str) or not archive:
                raise UpdateError(f"{label}: 'zip' muss ein Pfad oder eine URL sein.")
            if urlsplit(archive).scheme in ("http", "https"):
                source_zip = work / "archive.zip"
                download(archive, source_zip)
            else:
                source_zip = configured_path(archive, base)
            prefix = target.get("zip_prefix", "")
            if prefix:
                prefix = relative_path(prefix).as_posix() + "/"
            elif not isinstance(prefix, str):
                raise UpdateError("'zip_prefix' muss eine Zeichenkette sein.")
            count, total = 0, 0
            with zipfile.ZipFile(source_zip) as bundle:
                entries = bundle.infolist()
                if len(entries) > MAX_ENTRIES:
                    raise UpdateError("Zu viele ZIP-Einträge (max. 20000).")
                for number, entry in enumerate(entries):
                    # Validate even entries outside the selected prefix.
                    relative_path(entry.filename.rstrip("/"))
                    mode = entry.external_attr >> 16
                    if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                        raise UpdateError(f"Spezialdatei in ZIP nicht erlaubt: {entry.filename}")
                    if entry.is_dir() or not entry.filename.startswith(prefix):
                        continue
                    relative = relative_path(entry.filename[len(prefix):])
                    source = work / str(number)
                    with bundle.open(entry) as input_file, source.open("wb") as output:
                        total += copy_limited(input_file, output, MAX_BYTES - total)
                    add(source, root, relative, label)
                    count += 1
            if not count:
                raise UpdateError(f"{label}: Keine Dateien im ZIP unter {prefix!r} gefunden.")

    # Catch overlapping target roots (a file cannot also be another file's parent).
    for item in plan:
        if any(str(parent).casefold() in destinations for parent in item["destination"].parents):
            raise UpdateError(f"Kollidierende Zielpfade: {item['destination']}")
    return plan


def apply(plan):
    changes = [item for item in plan if item["action"] != "GLEICH"]
    # Refuse to overwrite edits made while the confirmation prompt was open.
    for item in plan:
        destination = item["destination"]
        ensure_safe_destination(destination)
        current = fingerprint(destination) if destination.exists() else None
        if current != item["old_hash"]:
            raise UpdateError(f"Zieldatei wurde seit der Vorschau verändert: {destination}")
    for item in changes:
        destination = item["destination"]
        ensure_safe_destination(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_name = None
        try:
            # Same filesystem as the destination: each replacement is atomic.
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".mc-update-", delete=False) as output:
                temp_name = output.name
                with item["source"].open("rb") as source:
                    shutil.copyfileobj(source, output)
            os.replace(temp_name, destination)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)
        print(f"Aktualisiert: {destination}")
    return len(changes)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Minecraft-Mods, Shader und Ressourcenpakete aktualisieren.")
    parser.add_argument("-c", "--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("-y", "-f", "--yes", "--force", action="store_true", dest="yes",
                        help="Änderungen ohne Rückfrage bestätigen (Sicherheitsprüfungen bleiben aktiv)")
    parser.add_argument("--dry-run", action="store_true", help="Nur herunterladen und Vorschau anzeigen")
    args = parser.parse_args(argv)
    try:
        config_path = args.config.expanduser().absolute()
        config = load_config(config_path)
        with tempfile.TemporaryDirectory(prefix="minecraft-updater-") as directory:
            plan = prepare(config, config_path.parent, Path(directory))
            print("\nVorschau:")
            for item in plan:
                print(f"  {item['action']:8} [{item['label']}] {item['destination']}")
            changed = sum(item["action"] != "GLEICH" for item in plan)
            print(f"\n{changed} neue/geänderte Datei(en), {len(plan) - changed} unverändert. Keine Löschungen.")
            if args.dry_run or not changed:
                return 0
            if not args.yes:
                try:
                    answer = input("Jetzt anwenden? [j/N] ").strip().lower()
                except EOFError:
                    answer = ""
                if answer not in ("j", "ja", "y", "yes"):
                    print("Abgebrochen. Zielordner wurden nicht verändert.")
                    return 0
            print(f"Fertig: {apply(plan)} Datei(en) aktualisiert.")
        return 0
    except (UpdateError, OSError, ValueError, zipfile.BadZipFile, RuntimeError, HTTPException) as error:
        print(f"Fehler: {error}", file=sys.stderr)
        print("Konfiguration prüfen; config.example.json zeigt Beispiele. Bei Schreibfehlern kann ein Teil bereits aktualisiert sein.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAbgebrochen. Falls das Schreiben bereits lief, können einzelne Dateien aktualisiert sein.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())

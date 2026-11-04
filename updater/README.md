# Minecraft-Updater

Kleiner Updater für **Windows und Linux/Steam Deck** (auch unter macOS nutzbar),
ohne zusätzliche Python-Pakete. Voraussetzung: **Python 3.9 oder neuer**.
Er installiert Dateien, nicht Minecraft selbst, Java oder einen Modloader.
Minecraft und den Launcher vor dem Update am besten schließen.

## Einrichtung

1. Diesen gesamten Ordner auf den Client kopieren.
2. `config.example.json` nach `config.json` kopieren.
3. Die Beispiel-URLs und Zielordner ersetzen; nicht benötigte Ziele entfernen.
   `example.com` ist nur ein Platzhalter und liefert keine echten Mods.
4. Den passenden Starter verwenden (siehe unten).

Die Konfiguration ist JSON, **ohne Kommentare und ohne Komma nach dem letzten
Eintrag**. Sie darf pro Client andere Zielpfade enthalten.

### Konfiguration

`targets` enthält beliebig viele Ziele. Pro Ziel ist **genau eine** Quellenart erlaubt:

**Einzelne URLs:**

```json
{
  "targets": [
    {
      "name": "Mods",
      "directory": "~/.minecraft/mods",
      "urls": [
        "https://dein-server.example/mods/mod-a.jar",
        {"url": "https://dein-server.example/download?id=42", "filename": "mod-b.jar"}
      ]
    }
  ]
}
```

Ohne `filename` wird der Dateiname aus dem URL-Pfad übernommen (nicht aus
HTTP-Headern). Mit `filename` kannst du ihn festlegen, auch mit Unterordnern,
z. B. `unterordner/datei.jar`. Nutze **direkte Download-URLs**, keine Webseiten
mit Download-Button. Weiterleitungen werden unterstützt; interaktive Anmeldung
und API-Authentifizierung nicht.

**ZIP-Datei, lokal oder als Download:**

```json
{
  "targets": [
    {
      "name": "Mods aus Clientpaket",
      "directory": "~/.minecraft/mods",
      "zip": "https://dein-server.example/clientpaket.zip",
      "zip_prefix": "clientpaket/mods"
    },
    {
      "name": "Ressourcenpakete",
      "directory": "~/.minecraft/resourcepacks",
      "zip": "pakete/clientpaket.zip",
      "zip_prefix": "resourcepacks"
    }
  ]
}
```

`zip_prefix` ist optional. Ohne Präfix wird der gesamte ZIP-Inhalt einschließlich
Unterordnern übernommen. Mit `"zip_prefix": "mods"` wird z. B. `mods/mod-a.jar`
zu `<Zielordner>/mod-a.jar`. Die Schreibweise muss exakt zum Archiv passen.
ZIP-Dateien im Archiv werden **nicht rekursiv entpackt**: Shader und Resourcepacks
sollen normalerweise als ZIP im Ziel liegen. Eine heruntergeladene einzelne
Shader-ZIP deshalb in `urls` eintragen; `zip` ist für ein äußeres Verteilarchiv.

Beide Quellenarten können in derselben Konfiguration für unterschiedliche Ziele
verwendet werden. Dieselbe Archiv-URL in mehreren Zielen wird je Ziel geladen.

### Zielpfade

- Relative Zielpfade und lokale ZIP-Pfade beziehen sich auf den Ordner der
  **Konfigurationsdatei**, nicht auf das aktuelle Arbeitsverzeichnis.
- `~` und Umgebungsvariablen werden expandiert; unter Windows z. B.
  `"%APPDATA%/.minecraft/mods"`, unter Linux `"$HOME/.minecraft/mods"`.
- Windows-Pfade am einfachsten mit `/` schreiben: `"C:/Games/Minecraft/mods"`.
  Bei Backslashes müssen diese in JSON verdoppelt werden.
- Standard-Windows: `%APPDATA%/.minecraft/{mods,shaderpacks,resourcepacks}`.
- Standard-Linux: `~/.minecraft/{mods,shaderpacks,resourcepacks}`.
- **Prism Launcher/Steam Deck:** den tatsächlichen `.minecraft`-Ordner der
  gewählten Instanz verwenden, nicht zwangsläufig `~/.minecraft`.
  In Prism lässt sich der Instanzordner über die Oberfläche öffnen.

## Starten

### Windows

Python 3 von python.org installieren (bei Bedarf „Add Python to PATH“ aktivieren).
Danach `update.bat` doppelklicken. Das Konsolenfenster bleibt für Vorschau,
Bestätigung und Ergebnis geöffnet.

### Steam Deck / Linux

Im Desktop-Modus zunächst `python3 --version` prüfen. Falls Python fehlt, muss es
über die für dein System geeignete Methode installiert werden.

1. Ordner z. B. nach `/home/deck/minecraft-updater` kopieren.
2. `chmod +x /home/deck/minecraft-updater/update.sh` ausführen
   (alternativ in den Dateieigenschaften „ausführbar“ aktivieren).
3. `Minecraft-Updater.desktop` auf den Desktop kopieren. Falls der Ordner anders
   heißt, darin `Exec=` anpassen. Pfade mit Leerzeichen in doppelte Anführungszeichen
   setzen, z. B. `Exec="/home/deck/Meine Tools/update.sh"`.
4. Die Desktop-Datei ggf. ausführbar machen und im Dateimanager als vertrauenswürdig
   markieren/„Ausführen erlauben“. Sie startet den Updater im Terminal.

Ein Doppelklick direkt auf `update.sh` kann je nach Dateimanager nur einen Editor
öffnen; für diesen Fall ist die `.desktop`-Datei gedacht. Unter macOS/Linux ist
auch der direkte Terminalaufruf möglich.

### Kommandozeile

```sh
python3 update.py                       # Vorschau, dann Rückfrage [j/N]
python3 update.py -y                    # ohne Rückfrage
python3 update.py -f                    # dasselbe wie -y
python3 update.py --dry-run             # herunterladen und prüfen, NICHT schreiben
python3 update.py -c /pfad/config.json   # andere Konfiguration
```

Unter Windows `py -3` statt `python3` verwenden. Die Starter reichen Argumente
weiter: `update.bat -y` bzw. `./update.sh -y`. Für einen automatischen Doppelklick
unter Windows eine Verknüpfung auf `update.bat` mit dem Argument `-y` anlegen;
unter Linux in der Desktop-Datei `Exec=/home/deck/minecraft-updater/update.sh -y`
setzen. Auch dann bleibt die Ergebnisanzeige bis Enter/Tastendruck sichtbar.

## Verhalten und Sicherheit

- Alle Quellen werden zuerst in einen temporären Ordner heruntergeladen/entpackt.
  Bei fehlerhaftem Download oder Archiv startet kein Schreiben in Zielordner.
- Die Vorschau zeigt `NEU`, `ERSETZEN` und `GLEICH` anhand von SHA-256-Vergleichen.
  Ohne `-y`/`-f` wird erst nach `j`/`ja`/`y`/`yes` geschrieben; Enter bricht ab.
- Identische Dateien bleiben unberührt. Fehlende Zielordner werden erst beim
  Anwenden erstellt. Die temporären Dateien werden anschließend entfernt.
- **Nicht aufgeführte Dateien werden nie gelöscht.** Ein Mod mit neuem Dateinamen
  entfernt nicht automatisch die alte Version! Alte Versionen selbst entfernen
  oder für Updates stabile Dateinamen (`filename`) verwenden.
- Jede Datei wird atomar ersetzt; es gibt **keine Gesamttransaktion, Backups oder
  automatische Rücknahme**. Bei Schreibfehlern/Stromausfall kann ein Teil bereits
  aktualisiert sein. Dann Fehler beheben und erneut starten. Wichtige Dateien sichern.
- Nach der Vorschau veränderte Dateien führen zum Abbruch. Nicht gleichzeitig
  mehrere Updater oder andere Programme auf denselben Zielordner schreiben lassen.
- Pfadtraversal, Windows-Spezialnamen, ZIP-Symlinks und symbolische Links/Junctions
  im Zielpfad werden abgewiesen. `-f` umgeht diese Prüfungen **nicht**.
- Maximal 2 GiB pro Download bzw. entpacktem ZIP-Inhalt je Ziel und 20.000
  ZIP-Einträge. Für große Pakete entsprechend freien temporären Speicher vorhalten.
- Nur vertrauenswürdige Quellen nutzen: Mods sind ausführbarer Code. SHA-256 dient
  hier dem Vergleich, **nicht** der Herkunftsprüfung. HTTPS bevorzugen.

## Tests

Im Ordner dieses Updaters, ohne externe Dienste oder zusätzliche Pakete:

```sh
python3 -m unittest -v
python3 -m py_compile update.py test_update.py
sh -n update.sh
```

Die Tests verwenden einen lokalen HTTP-Server und temporäre Zielordner.

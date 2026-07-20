# Projekt: Prisma (Token-Konverter)

Flask-App, lokaler Dokument- und Format-Konverter. Laeuft ausschliesslich auf
127.0.0.1:8770. Alle Nutzerdaten und Verarbeitung bleiben strikt lokal.
Der Quellcode ist auf GitHub (NiklasS2028/prisma-local) veroeffentlicht.

## Stack
- Backend: Flask (Python)
- Frontend: Vanilla JS (kein Framework, kein Build)
- Dokumente: python-docx, python-pptx
- OCR/PDF: Tesseract und poppler, gebuendelt mitgeliefert
- Packaging: PyInstaller (onedir)

## Teststand
Aktuell: 145 Tests / 13 Suiten. Diese Zeile bei jeder Aenderung am Testumfang
mitfuehren.

## Pre-Push-Checkliste
Vor jedem Push pruefen. Die Punkte sind Pflicht, nicht optional.

- git-Historie pruefen auf versehentlich getrackte Artefakte: stats.json,
  outputs/, uploads/, prisma_*.md, "Arbeitsanweisung claude code.txt"
- Google Fonts lokal gebuendelt inkl. der zugehoerigen OFL-Lizenzdateien
- stats.json atomar schreiben: in temp-Datei schreiben, dann os.replace
- Origin-Check auf allen stats-Endpoints (nur lokale Herkunft zulassen)
- uploads-Purge beim Serverstart (Altbestand loeschen)
- outputs im Reset-Pattern verwalten (definierter Ausgangszustand)
- README mit aktuellen Playwright-Screenshots aus tests/screenshots/

## Sicherheit
- Keine Netzwerkaufrufe nach aussen. Verarbeitung strikt lokal.
- Keine Secrets committen. Artefakte gehoeren nicht in die git-Historie.

## Offene Punkte
- Notes sind deutsch-only, d.note wird roh angezeigt (index.html:1602).
  Lokalisierung braeuchte einen lang-Parameter durch convert_file bis
  extract_pdf. Eigener Block, nicht Teil der Struktur-Commits.
- Plural-Bug '1 Seiten' in index.html:1196 (statPages, JavaScript). Der
  deutsche Plural-Helfer _plural liegt in converter.py (Python), teilt sich
  also nicht mit der JS-Stelle. Trivialer Einzeiler, separat zu fixen.

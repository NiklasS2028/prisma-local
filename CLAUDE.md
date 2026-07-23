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
Aktuell: 212 Tests / 16 Suiten. Diese Zeile bei jeder Aenderung am Testumfang
mitfuehren.

## CI
GitHub Actions (`.github/workflows/tests.yml`) laeuft bei jedem Push und Pull
Request auf `main`. Umfang bewusst begrenzt: die 5 serverlosen Suiten
(test_block1, test_block2, test_blockI_batch, test_pdf_struct, test_pdf_robust,
zusammen 78 Tests) auf ubuntu-latest mit Tesseract und poppler. Die 2 HTTP- und
9 Playwright-Suiten laufen nur lokal, damit kein rotes Badge aus Infrastruktur
statt echten Fehlern entsteht. Die Gesamtzahl 212/16 ist der volle lokale Stand.

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
Derzeit keine. (Notes-Lokalisierung: erledigt in Block H, Fehlertexte in
Block I. Plural-Bug '1 Seiten': gefixt in Block G.)

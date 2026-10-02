.PHONY: help setup api web dev test lint marker labels synth-video record bench ocr-smoke probe

PYTHON ?= .venv/bin/python
UVICORN ?= .venv/bin/uvicorn
PYTEST ?= .venv/bin/pytest
RUFF ?= .venv/bin/ruff

help:
	@echo "BilletVision Makefile targets:"
	@echo "  help         - Show this help message"
	@echo "  setup        - Create backend virtualenv, install deps, download OCR models"
	@echo "  api          - Start backend FastAPI server on port 8000"
	@echo "  web          - Start Next.js web dashboard on port 3000"
	@echo "  dev          - Start backend and frontend concurrently"
	@echo "  test         - Run pytest test suite"
	@echo "  lint         - Run ruff on backend and lint/tsc on frontend"
	@echo "  marker       - Generate printable ArUco marker PNG"
	@echo "  labels       - Generate printable ID labels with QR"
	@echo "  synth-video  - Generate synthetic demo video"
	@echo "  record       - Record video from camera for 60 seconds"
	@echo "  bench        - Run synthetic benchmark"
	@echo "  ocr-smoke    - Run RapidOCR smoke test"
	@echo "  probe        - Run WebSocket probe script"

setup:
	cd backend && (test -d .venv || /opt/homebrew/bin/python3.11 -m venv .venv || python3.11 -m venv .venv || python3 -m venv .venv)
	cd backend && $(PYTHON) -m pip install --upgrade pip && $(PYTHON) -m pip install -r requirements.txt
	cd backend && $(PYTHON) -m tools.ocr_smoke
	@if [ -d web ] && [ -f web/package.json ]; then cd web && npm install; fi

api:
	cd backend && $(UVICORN) billetvision.api.main:app --port 8000

web:
	cd web && npm run dev

dev:
	$(MAKE) -j2 api web

test:
	cd backend && $(PYTEST) -q

lint:
	cd backend && $(RUFF) check .
	@if [ -d web ] && [ -f web/package.json ]; then cd web && npm run lint && npx tsc --noEmit; fi

marker:
	cd backend && $(PYTHON) -m tools.make_marker --mm 80 --out ../print/marker_80mm.png

labels:
	cd backend && $(PYTHON) -m tools.make_labels --ids ../data/props.csv --out ../print/

synth-video:
	cd backend && $(PYTHON) -m tools.gen_synth_video --out ../data/videos/synth_demo.mp4

record:
	cd backend && $(PYTHON) -m tools.record_video --seconds 60 --out ../data/videos/real_demo.mp4

bench:
	cd backend && $(PYTHON) -m tools.bench_synthetic --n 200

ocr-smoke:
	cd backend && $(PYTHON) -m tools.ocr_smoke

probe:
	cd backend && $(PYTHON) ../scripts/ws_probe.py --seconds 10

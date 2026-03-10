.PHONY: run setup

run:
	python3 app.py

setup:
	python3 -m pip install -r requirements.txt
	cp -n .env.example .env || true

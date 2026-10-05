.PHONY: run import sync test
run:
	python3 server.py
import:
	python3 scripts/import_snapshot.py
sync:
	python3 scripts/import_snapshot.py --fetch
test:
	python3 -m unittest discover -s tests

.PHONY: run import sync import-local package-prod publish test
run:
	python3 server.py
import:
	python3 scripts/import_snapshot.py
# Production refresh path (local rebuilt classic pages). Do not fetch frozen bold-tulip.
sync: import-local
import-local:
	python3 scripts/import_snapshot.py --local-dashboard
package-prod:
	python3 scripts/package_prod_dist.py
publish: package-prod
	bash dashboard/publish.sh
test:
	python3 -m unittest discover -s tests

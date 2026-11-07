PYTHON ?= python3.12
COMPOSE ?= docker compose -p fneo-public-repro -f docker-compose.yml

.PHONY: environment verify-inputs reproduce verify-outputs validate-ontology reproduce-clean

environment:
	$(PYTHON) -c "import sys; assert sys.version.startswith('3.12.13'), sys.version"

verify-inputs:
	$(PYTHON) reproduction/verify_inputs.py

verify-outputs:
	$(PYTHON) reproduction/verify_outputs.py

validate-ontology:
	docker compose -f docker-compose.ontology-validation.yml build
	FNEO_FORCE_ROBOT=1 $(PYTHON) validation/run_ontology_validation.py

# Clean reproduction. Scientific checks live in reproduction/reproduce_clean.py.
# The wrapper performs the surrounding environment steps and always removes
# the disposable database.
reproduce-clean:
	@test -n "$$FNEO_NEO4J_PASSWORD" || (echo "Set FNEO_NEO4J_PASSWORD for the disposable container." && exit 1)
	@echo "1 pin Python 3.12.13"
	@$(PYTHON) -c "import sys; assert sys.version.startswith('3.12.13'), sys.version"
	@echo "2 create local virtual environment if needed"
	@test -x .venv/bin/python || $(PYTHON) -m venv .venv
	@echo "3 install pinned Python dependencies"
	@.venv/bin/pip install -q -r requirements-lock.txt
	@echo "4 verify operational input checksums"
	@.venv/bin/python reproduction/verify_inputs.py
	@echo "5 start disposable Neo4j 5.9.0 on port 17689"
	FNEO_NEO4J_PASSWORD="$$FNEO_NEO4J_PASSWORD" $(COMPOSE) up -d --wait
	@echo "6 import operational graphs"
	@echo "7 extract document bundles"
	@echo "8 baseline decisions"
	@echo "9 refined decisions"
	@echo "10 repeat refined decisions"
	@echo "11 census"
	@echo "12 headline fractions"
	@echo "13 six publication-view checksums"
	@echo "14 Turtle parse"
	@echo "15 ROBOT 1.9.11 profile"
	@echo "16 HermiT consistency"
	@echo "17 SHACL"
	@echo "18 competency questions FDQ-001 through FDQ-005"
	@echo "19 compare baseline, refined, and repeated refined outputs"
	@echo "20 write the reproduction report"
	FNEO_CLEAN=1 FNEO_FORCE_ROBOT=1 \
		FNEO_REPRO_NEO4J_URI="bolt://127.0.0.1:17689" \
		FEO_NEO4J_PASSWORD="$$FNEO_NEO4J_PASSWORD" \
		FNEO_NEO4J_PASSWORD="$$FNEO_NEO4J_PASSWORD" \
		.venv/bin/python reproduction/reproduce_clean.py; \
	status=$$?; \
	echo "21 stop disposable Neo4j"; \
	$(COMPOSE) down -v; \
	echo "22 confirm the research port 7687 was not the reproduction URI"; \
	echo "23 exit with the reproduction status"; \
	exit $$status

PYTHON := python3
SYSTEMD_SYSTEM := /etc/systemd/system

all: build

build:
	$(PYTHON) setup.py build

lint:
	$(PYTHON) -mtox -e flake8

test:
	$(PYTHON) -mtox

test-quick:
	$(PYTHON) -mtox -e black,flake8,pytest-quick

black-check:
	$(PYTHON) -mtox -e black

black:
	$(PYTHON) -mtox -e black-reformat

install: build
	$(PYTHON) setup.py install

install-systemd:
	install -m 0644 turku-storage-update-config.service $(SYSTEMD_SYSTEM)/turku-storage-update-config.service
	install -m 0644 turku-storage-update-config.timer $(SYSTEMD_SYSTEM)/turku-storage-update-config.timer
	systemctl enable turku-storage-update-config.timer
	systemctl start turku-storage-update-config.timer

clean:
	$(PYTHON) setup.py clean
	$(RM) -r build MANIFEST

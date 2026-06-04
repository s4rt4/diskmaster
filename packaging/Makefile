# DiskMaster install rules — the single source of truth for what goes where.
# Every package format (deb/rpm/AUR/flatpak/tarball) just calls `make install`
# with an appropriate DESTDIR/PREFIX, so the file list lives in exactly one place.
#
#   make install DESTDIR=/path/to/stage PREFIX=/usr
#   make uninstall PREFIX=/usr            # remove an in-place install

VERSION  := 0.1.0
PREFIX   ?= /usr
DESTDIR  ?=

ROOT     := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)
SRC      := $(ROOT)/diskmaster

APPDIR   := $(DESTDIR)$(PREFIX)/lib/diskmaster
BINDIR   := $(DESTDIR)$(PREFIX)/bin
LIBEXEC  := $(DESTDIR)$(PREFIX)/libexec/diskmaster
POLKITD  := $(DESTDIR)$(PREFIX)/share/polkit-1/actions
DESKTOPD := $(DESTDIR)$(PREFIX)/share/applications
ICONDIR  := $(DESTDIR)$(PREFIX)/share/icons/hicolor/scalable/apps
LICENSED := $(DESTDIR)$(PREFIX)/share/licenses/diskmaster

.PHONY: install uninstall version

version:
	@echo $(VERSION)

install:
	# --- application code (everything but caches and the proprietary binary) ---
	install -d "$(APPDIR)"
	cp -r "$(SRC)/." "$(APPDIR)/"
	find "$(APPDIR)" -name '__pycache__' -type d -prune -exec rm -rf {} +
	rm -rf "$(APPDIR)/assets/hdsentinel"
	# --- user launcher: /usr/bin/diskmaster ---
	install -d "$(BINDIR)"
	sed 's|@APPROOT@|$(PREFIX)/lib/diskmaster|g' "$(ROOT)/packaging/diskmaster.in" \
		> "$(BINDIR)/diskmaster"
	chmod 0755 "$(BINDIR)/diskmaster"
	# --- pkexec wrapper anchored by the polkit action ---
	install -d "$(LIBEXEC)"
	install -m 0755 "$(ROOT)/packaging/diskmaster-helper" "$(LIBEXEC)/diskmaster-helper"
	# --- polkit action, desktop entry, icon ---
	install -d "$(POLKITD)" "$(DESKTOPD)" "$(ICONDIR)"
	install -m 0644 "$(ROOT)/packaging/polkit/com.diskmaster.policy" \
		"$(POLKITD)/com.diskmaster.policy"
	install -m 0644 "$(ROOT)/packaging/diskmaster.desktop" \
		"$(DESKTOPD)/diskmaster.desktop"
	install -m 0644 "$(SRC)/assets/icons/diskmaster.svg" \
		"$(ICONDIR)/diskmaster.svg"
	# --- license (also the canonical Arch path) ---
	install -d "$(LICENSED)"
	install -m 0644 "$(ROOT)/LICENSE" "$(LICENSED)/LICENSE"

uninstall:
	rm -rf "$(DESTDIR)$(PREFIX)/lib/diskmaster"
	rm -f  "$(BINDIR)/diskmaster"
	rm -rf "$(DESTDIR)$(PREFIX)/libexec/diskmaster"
	rm -f  "$(POLKITD)/com.diskmaster.policy"
	rm -f  "$(DESKTOPD)/diskmaster.desktop"
	rm -f  "$(ICONDIR)/diskmaster.svg"
	rm -rf "$(LICENSED)"

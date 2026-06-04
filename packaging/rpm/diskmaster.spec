Name:           diskmaster
Version:        0.1.0
Release:        1%{?dist}
Summary:        HDD/SSD/NVMe health monitor with a Hard Disk Sentinel-style UI

# No LICENSE file is shipped yet — set this to the real SPDX id before release.
License:        LicenseRef-Unspecified
URL:            https://github.com/s4rt4/diskmaster
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3 >= 3.11
Requires:       python3-pyqt6
Requires:       polkit
Requires:       smartmontools
Recommends:     nvme-cli
Recommends:     libnotify

%description
DiskMaster is a PyQt6 desktop monitor for disk health, temperature and
S.M.A.R.T. data, with a Hard Disk Sentinel-style interface: per-disk cards,
history charts, self-tests and threshold alerts.

The proprietary HDSentinel CLI is not bundled; install it separately from
hdsentinel.com to enable that backend. smartctl works out of the box.

%prep
%autosetup -n %{name}-%{version}

%build
# Pure Python; nothing to compile at build time.

%install
make -C packaging install DESTDIR=%{buildroot} PREFIX=%{_prefix}

%files
%{_bindir}/diskmaster
%{_prefix}/lib/diskmaster/
%{_libexecdir}/diskmaster/
%{_datadir}/polkit-1/actions/com.diskmaster.policy
%{_datadir}/applications/diskmaster.desktop
%{_datadir}/icons/hicolor/scalable/apps/diskmaster.svg

%changelog
* Wed Jun 04 2026 s4rt4 <vinvan83@gmail.com> - 0.1.0-1
- Initial RPM packaging.

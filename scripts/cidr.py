#!/usr/bin/env python3
"""Build exact CN CIDRs from a local DB-IP Country Lite CSV.gz (stdlib only)."""
import argparse
import csv
import gzip
import hashlib
import ipaddress as ip
import datetime
import tempfile
import urllib.request
from pathlib import Path
import re


def merged(ranges):
    result = []
    for start, end in sorted(ranges):
        if result and start <= result[-1][1] + 1:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def build(source, release):
    ranges = {4: [], 6: []}
    counts = {4: 0, 6: 0}
    last = {}
    rows = 0
    with gzip.open(source, 'rt', encoding='utf-8', newline='') as stream:
        for row in csv.reader(stream):
            rows += 1
            if len(row) != 3:
                raise ValueError(f'Invalid CSV row {rows}')
            start, end = ip.ip_address(row[0]), ip.ip_address(row[1])
            version = start.version
            if version != end.version or int(start) > int(end):
                raise ValueError(f'Invalid IP interval at row {rows}')
            if int(start) <= last.get(version, -1):
                raise ValueError(f'Overlapping or unsorted source at row {rows}')
            last[version] = int(end)
            if row[2] == 'CN':
                ranges[version].append((int(start), int(end)))
                counts[version] += 1
    networks = {}
    stats = {}
    for version, address in [(4, ip.IPv4Address), (6, ip.IPv6Address)]:
        if not ranges[version]:
            raise ValueError(f'No CN IPv{version} records')
        intervals = merged(ranges[version])
        nets = [net for start, end in intervals
                for net in ip.summarize_address_range(address(start), address(end))]
        # Exact interval equality proves neither extra addresses nor missing addresses.
        reconstructed = merged([(int(n.network_address), int(n.broadcast_address)) for n in nets])
        if reconstructed != intervals:
            raise ValueError('CIDR coverage differs from source')
        if nets != list(ip.collapse_addresses(nets)):
            raise ValueError('CIDRs are not minimally aggregated')
        networks[version] = [str(n) for n in nets]
        stats[f'ipv{version}'] = {
            'source_cn_rows': counts[version], 'cidr_count': len(nets),
            'address_count': str(sum(end - start + 1 for start, end in intervals)),
        }
    lines = ["# Joe CN CIDR — DIRECT fallback", f"# Release: {release}",
        "# IP Geolocation by DB-IP (https://db-ip.com)",
        "# License: CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/",
        "# License text: LICENSE-CIDR.txt",
        "# Changes: selected CN; exact range-to-CIDR conversion and aggregation.",
        f"# Source: https://download.db-ip.com/free/dbip-country-lite-{release}.csv.gz",
        f"# Source SHA256: {hashlib.sha256(source.read_bytes()).hexdigest()}"]
    for version in (4, 6):
        lines += ["", f"# ===== IPv{version} ({len(networks[version])}) ====="]
        kind = "IP-CIDR" if version == 4 else "IP-CIDR6"
        lines += [f"{kind},{net}" for net in networks[version]]
    return "\n".join(lines) + "\n"


def check(text):
    groups = {4: [], 6: []}
    for line in text.splitlines():
        if not line or line.startswith('#'): continue
        kind, value = line.split(',')
        net = ip.ip_network(value, strict=True)
        if kind != {4: 'IP-CIDR', 6: 'IP-CIDR6'}[net.version]:
            raise ValueError('Address family mismatch')
        if net.prefixlen == 0: raise ValueError('Default route is forbidden')
        groups[net.version].append(net)
    for nets in groups.values():
        if not nets or nets != list(ip.collapse_addresses(nets)):
            raise ValueError('Empty, overlapping, unsorted or nonminimal CIDRs')
    return {v: sum(n.num_addresses for n in nets) for v, nets in groups.items()}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['check', 'update'])
    p.add_argument('--source', type=Path)
    p.add_argument('--release', default=datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m'))
    p.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'cn-cidr.list')
    args = p.parse_args()
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', args.release): p.error('Invalid release')
    before = args.output.read_text() if args.output.exists() else None
    if args.command == 'check':
        print(check(before)); return
    if args.source:
        result = build(args.source, args.release)
    else:
        if before and f'# Release: {args.release}\n' in before:
            check(before); print('Current monthly release already present.'); return
        url = f'https://download.db-ip.com/free/dbip-country-lite-{args.release}.csv.gz'
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.csv.gz'
            with urllib.request.urlopen(url, timeout=120) as response, source.open('wb') as out:
                import shutil
                shutil.copyfileobj(response, out)
            result = build(source, args.release)
    coverage = check(result)
    if before:
        old = check(before)
        if any(abs(coverage[v] - old[v]) > old[v] * 0.1 for v in old):
            raise ValueError('Address coverage changed by more than 10%; manual review required')
    args.output.write_text(result)
    print('Validated exact CN coverage:', coverage)


if __name__ == '__main__': main()

#!/usr/bin/env python3
"""Add HTTP access by VPS IPv4 without rewriting existing domain/TLS sites."""
import argparse, ipaddress, json, os, re, subprocess, tempfile, time
from pathlib import Path
from urllib.request import urlopen

MARKER='# Gems POS HTTP IP site v1'

def ipv4(value):
    ip=ipaddress.IPv4Address(value)
    if ip.is_unspecified or ip.is_multicast or ip.is_loopback:
        raise ValueError('Use the VPS IPv4 address, not a loopback/multicast address.')
    return str(ip)

def discover_addresses(provided=''):
    if provided:return [ipv4(provided)]
    ips=[]
    try:
        r=subprocess.run(['ip','-j','-4','address','show'],check=True,capture_output=True,text=True)
        for interface in json.loads(r.stdout):
            for info in interface.get('addr_info',[]):
                candidate=ipaddress.IPv4Address(info.get('local','0.0.0.0'))
                if candidate.is_global:ips.append(str(candidate))
    except (OSError,ValueError,subprocess.CalledProcessError):pass
    if not ips:
        try:
            with urlopen('https://api.ipify.org',timeout=10) as r:ips=[ipv4(r.read(64).decode().strip())]
        except Exception as exc:
            raise ValueError('Cannot detect the VPS public IPv4. Retry with --ip YOUR_VPS_IP.') from exc
    return sorted(set(ips))

def render_site(ips,target):
    names=' '.join([*(ipv4(ip) for ip in ips),'127.0.0.1','_'])
    return f'''{MARKER}
# Project: {target}
server {{
    listen 80;
    server_name {names};
    client_max_body_size 4m;
    location = / {{ return 302 /gems; }}
    location /gems-maintenance/ {{
        client_max_body_size 1024m;
        proxy_pass http://127.0.0.1:8099;
        proxy_read_timeout 1900s;
        proxy_send_timeout 1900s;
        proxy_request_buffering off;
        proxy_set_header Authorization $http_authorization;
    }}
    location / {{
        proxy_pass http://127.0.0.1:8070;
        proxy_set_header Host $http_host;
        proxy_set_header X-Forwarded-Host $http_host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }}
}}
'''

def atomic_write(path,data):
    fd,name=tempfile.mkstemp(prefix='.gems-ip-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data)
        os.chmod(name,0o644)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def configure(target,ips,nginx_root=Path('/etc/nginx'),run=subprocess.run):
    target=Path(target).resolve()
    if not re.fullmatch(r'/[A-Za-z0-9._/-]+',str(target)) or not (target/'compose.yml').is_file():
        raise ValueError('Existing Gems project folder required.')
    available=nginx_root/'sites-available';enabled=nginx_root/'sites-enabled'
    available.mkdir(parents=True,exist_ok=True);enabled.mkdir(parents=True,exist_ok=True)
    site=available/'gems-pos-ip';link=enabled/'00-gems-pos-ip'
    if site.is_symlink():raise ValueError('IP site path is a symlink; no unrelated configuration changed.')
    old=site.read_bytes() if site.exists() else None
    if old is not None and (not old.startswith(MARKER.encode()) or ('# Project: '+str(target)+'\n').encode() not in old):
        raise ValueError('IP site already belongs to another configuration/project.')
    if os.path.lexists(link) and (not link.is_symlink() or link.resolve()!=site.resolve()):
        raise ValueError('IP site activation path already belongs to another configuration.')
    had_link=os.path.lexists(link)
    if old is not None:
        backup=target/'backups';backup.mkdir(exist_ok=True)
        p=backup/f'nginx-ip-before-{time.time_ns()}.conf';p.write_bytes(old);p.chmod(0o600)
    atomic_write(site,render_site(ips,target).encode())
    if not had_link:link.symlink_to(site)
    try:
        run(['nginx','-t'],check=True)
        run(['systemctl','enable','--now','nginx'],check=True)
        run(['systemctl','reload','nginx'],check=True)
    except Exception:
        if old is None:site.unlink(missing_ok=True)
        else:atomic_write(site,old)
        if not had_link:link.unlink(missing_ok=True)
        raise
    (target/'.http-ip').write_text(ips[0]+'\n')
    print(f'Ready: http://{ips[0]}/gems (http://{ips[0]} redirects to /gems)')
    return ips[0]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('target');parser.add_argument('--ip',default='')
    args=parser.parse_args()
    if os.geteuid()!=0:raise SystemExit('Run as root.')
    try:
        ips=discover_addresses(args.ip)
        configure(Path(args.target),ips)
    except (ValueError,subprocess.CalledProcessError) as exc:raise SystemExit(str(exc))
    # Leave the cloud firewall and SSH configuration unchanged. If UFW is already
    # active, allow only the HTTP service port needed for this installer.
    if subprocess.run(['sh','-c','command -v ufw >/dev/null'],check=False).returncode==0:
        result=subprocess.run(['ufw','status'],capture_output=True,text=True)
        if 'Status: active' in result.stdout:subprocess.run(['ufw','allow','80/tcp'],check=True)

if __name__=='__main__':main()

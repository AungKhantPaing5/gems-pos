#!/usr/bin/env python3
"""Configure an optional domain site without replacing existing site definitions."""
import argparse, os, re, subprocess, tempfile
from pathlib import Path
MARKER='# Gems POS optional domain site v1'

def valid_domain(value):
    value=value.lower()
    labels=value.split('.')
    if len(value)>253 or len(labels)<2 or not re.fullmatch('[a-z]{2,63}',labels[-1]):
        raise ValueError('Use a domain name without http://, paths or ports.')
    if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',s) for s in labels):
        raise ValueError('Invalid domain label.')
    return value

def render(domain):
    domain=valid_domain(domain)
    return f'''{MARKER}
server {{
    listen 80;
    server_name {domain};
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

def configure(domain,root=Path('/etc/nginx'),run=subprocess.run):
    domain=valid_domain(domain)
    available=root/'sites-available';enabled=root/'sites-enabled'
    available.mkdir(parents=True,exist_ok=True);enabled.mkdir(parents=True,exist_ok=True)
    site=available/('gems-domain-'+domain);link=enabled/site.name
    if site.is_symlink():raise ValueError('Domain site is a symlink; refusing to overwrite.')
    if site.exists() and not site.read_text().startswith(MARKER):
        raise ValueError('Domain site belongs to another configuration.')
    if os.path.lexists(link) and (not link.is_symlink() or link.resolve()!=site.resolve()):
        raise ValueError('Domain activation path belongs to another configuration.')
    # Search the effective configuration, including sites outside sites-enabled.
    effective=run(['nginx','-T'],capture_output=True,text=True,check=True).stdout
    sections=re.split(r'^# configuration file (.+):\s*$',effective,flags=re.M)
    for i in range(1,len(sections),2):
        path=Path(sections[i]).resolve()
        if path==site.resolve():continue
        body=re.sub(r'#.*','',sections[i+1])
        for names in re.findall(r'\bserver_name\s+([^;]+);',body):
            if domain in names.split():
                raise ValueError(f'{domain} already has a site in {path}. Use the manual existing-site instructions in HTTPS.md.')
    created=not site.exists();had_link=os.path.lexists(link)
    if created:
        fd,name=tempfile.mkstemp(prefix='.gems-domain-',dir=available)
        try:
            with os.fdopen(fd,'w') as f:f.write(render(domain))
            os.chmod(name,0o644);os.replace(name,site)
        finally:
            if os.path.exists(name):os.unlink(name)
    if not had_link:link.symlink_to(site)
    try:
        run(['nginx','-t'],check=True)
        run(['systemctl','reload','nginx'],check=True)
    except Exception:
        if not had_link:link.unlink(missing_ok=True)
        if created:site.unlink(missing_ok=True)
        raise
    # Existing owned files may have Certbot TLS edits: keep them on repeated runs.
    return site

def main():
    p=argparse.ArgumentParser();p.add_argument('domain');args=p.parse_args()
    if os.geteuid()!=0:raise SystemExit('Run as root.')
    try:configure(args.domain)
    except (ValueError,subprocess.CalledProcessError) as exc:raise SystemExit(str(exc))
if __name__=='__main__':main()

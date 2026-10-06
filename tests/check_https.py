"""Optional domain setup: routing, conflict guards, retries and rollback."""
import importlib.util, tempfile, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('domain',ROOT/'scripts/configure-domain.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert m.valid_domain('Shop.Example.com')=='shop.example.com'
for value in ['http://example.com','example.com/x','-shop.example.com','shop-.example.com','bad;id','example..com','example.com:80']:
    try:m.valid_domain(value)
    except ValueError:pass
    else:raise AssertionError(value)
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);calls=[]
    def run(args,**kw):calls.append(args);return subprocess.CompletedProcess(args,0,'# configuration file /other.conf:\nserver_name other.example.com;\n')
    site=m.configure('shop.example.com',root,run);link=root/'sites-enabled'/site.name
    assert link.resolve()==site
    text=site.read_text();assert 'server_name shop.example.com;' in text and '127.0.0.1:8070' in text and '127.0.0.1:8099' in text
    assert 'return 302 /gems;' in text and 'X-Forwarded-Proto $scheme' in text
    site.write_text(text+'# Certbot TLS configuration fixture\n')
    m.configure('shop.example.com',root,run)
    assert site.read_text().endswith('# Certbot TLS configuration fixture\n')
    def conflict(args,**kw):return subprocess.CompletedProcess(args,0,'# configuration file /other.conf:\nserver_name shop.example.com;\n')
    try:m.configure('shop.example.com',root,conflict)
    except ValueError:pass
    else:raise AssertionError('Missed existing domain site')
    def fail(args,**kw):
        if args==['nginx','-t']:raise subprocess.CalledProcessError(1,args)
        return subprocess.CompletedProcess(args,0,'')
    try:m.configure('new.example.com',root,fail)
    except subprocess.CalledProcessError:pass
    else:raise AssertionError('Validation should fail')
    assert not (root/'sites-available/gems-domain-new.example.com').exists()
    assert not (root/'sites-enabled/gems-domain-new.example.com').is_symlink()
    site.write_text('unrelated configuration')
    try:m.configure('shop.example.com',root,run)
    except ValueError:pass
    else:raise AssertionError('Overwrote unowned site')
    assert site.read_text()=='unrelated configuration'
print('Passed domain validation, maintenance/app routing, existing-site conflict guard, TLS-preserving retry and rollback.')

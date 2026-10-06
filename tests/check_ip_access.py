"""Exercise the HTTP site using temporary projects and mocked system commands."""
import importlib.util, subprocess, tempfile, json
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ip_access',ROOT/'scripts/configure-ip-access.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert m.discover_addresses('203.0.113.10')==['203.0.113.10']
for bad in ['bad;id','127.0.0.1','0.0.0.0','::1','224.0.0.1']:
    try:m.discover_addresses(bad)
    except ValueError:pass
    else:raise AssertionError(bad)
with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,json.dumps([{'addr_info':[{'local':'8.8.8.8'}]}]))),patch.object(m,'urlopen') as web:
    assert m.discover_addresses()==['8.8.8.8'];web.assert_not_called()
with patch.object(m.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'[]')),patch.object(m,'urlopen') as web:
    web.return_value.__enter__.return_value.read.return_value=b'203.0.113.10'
    assert m.discover_addresses()==['203.0.113.10']
with tempfile.TemporaryDirectory(prefix='gems-ip-test-') as tmp:
    base=Path(tmp);target=base/'shop';target.mkdir();(target/'compose.yml').write_text('keep compose')
    nginx=base/'nginx';(nginx/'sites-available').mkdir(parents=True);(nginx/'sites-enabled').mkdir()
    unrelated=nginx/'sites-available/other';unrelated.write_text('unrelated domain config')
    calls=[]
    def run(args,**kwargs):calls.append(args);return subprocess.CompletedProcess(args,0)
    m.configure(target,['203.0.113.10'],nginx,run)
    site=nginx/'sites-available/gems-pos-ip';link=nginx/'sites-enabled/00-gems-pos-ip'
    text=site.read_text();assert 'server_name 203.0.113.10 127.0.0.1 _;' in text
    assert 'return 302 /gems;' in text and '127.0.0.1:8070' in text and '127.0.0.1:8099' in text
    assert 'https://' not in text and 'ssl' not in text and 'default_server' not in text
    assert link.resolve()==site and unrelated.read_text()=='unrelated domain config'
    assert calls==[['nginx','-t'],['systemctl','enable','--now','nginx'],['systemctl','reload','nginx']]
    old=site.read_bytes()
    def fail(args,**kwargs):raise subprocess.CalledProcessError(1,args)
    try:m.configure(target,['203.0.113.11'],nginx,fail)
    except subprocess.CalledProcessError:pass
    else:raise AssertionError('Expected validation failure')
    assert site.read_bytes()==old and link.is_symlink()
    assert (target/'.http-ip').read_text()=='203.0.113.10\n'
    assert list((target/'backups').glob('nginx-ip-before-*.conf'))
    site.write_text('owned by someone else')
    try:m.configure(target,['203.0.113.10'],nginx,run)
    except ValueError:pass
    else:raise AssertionError('Unrelated site was overwritten')
    assert site.read_text()=='owned by someone else'
    site.unlink();link.unlink()
    try:m.configure(target,['203.0.113.10'],nginx,fail)
    except subprocess.CalledProcessError:pass
    assert not site.exists() and not link.is_symlink()
print('Passed IPv4 detection/validation, HTTP routing, unrelated-site preservation, ownership checks and validation rollback.')

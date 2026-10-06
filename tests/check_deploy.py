"""Actual deployment scripts with fake Docker/network; no apt/systemd calls."""
from pathlib import Path
import tempfile,shutil,os,subprocess,tarfile,json
ROOT=Path(__file__).resolve().parents[1]
assert os.geteuid()==0,'Run isolated deployment tests as root in a disposable environment.'
with tempfile.TemporaryDirectory(prefix='gems-deploy-test-') as tmp:
 base=Path(tmp);bin=base/'bin';bin.mkdir();log=base/'docker.log'
 fake=bin/'docker';fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$GEMS_TEST_LOG"\nexit 0\n');fake.chmod(0o755)
 uname=bin/'uname';uname.write_text('#!/bin/sh\necho Microsoft-WSL\n');uname.chmod(0o755)
 env=dict(os.environ,PATH=str(bin)+':'+os.environ['PATH'],GEMS_TEST_LOG=str(log))
 target=base/'shop';(target/'addons/gems_pos').mkdir(parents=True);(target/'scripts').mkdir()
 (target/'addons/gems_pos/old-marker.txt').write_text('old addon')
 (target/'compose.yml').write_text('existing compose sentinel\n');(target/'.env').write_text('existing environment sentinel\n')
 (target/'customer-data.txt').write_text('existing customer fixture')
 (target/'scripts/backup.sh').write_text('#!/bin/sh\necho backup-first >> "$GEMS_TEST_LOG"\n')
 r=subprocess.run(['bash',str(ROOT/'deploy.sh'),'--target',str(target),'--ip','203.0.113.10'],env=env,capture_output=True,text=True)
 assert r.returncode==0,(r.stdout,r.stderr)
 assert (target/'compose.yml').read_text()=='existing compose sentinel\n'
 assert (target/'.env').read_text()=='existing environment sentinel\n'
 assert (target/'customer-data.txt').read_text()=='existing customer fixture'
 assert (target/'addons/gems_pos/controllers/reports.py').exists()
 actions=log.read_text();assert actions.index('backup-first')<actions.index('compose stop odoo')
 assert '-u gems_pos --stop-after-init' in actions and 'down' not in actions and '-i gems_pos' not in actions
 assert (target/'scripts/backup.sh').read_text().startswith('#!/bin/sh'), 'Existing operational scripts replaced'
 # Exercise the VPS branch with an isolated helper stub, never touching host Nginx.
 cloudkit=base/'cloudkit';cloudkit.mkdir();(cloudkit/'scripts').mkdir()
 for name in ['deploy.sh','apply-update.sh']:shutil.copyfile(ROOT/name,cloudkit/name)
 shutil.copytree(ROOT/'addons',cloudkit/'addons')
 (cloudkit/'scripts/configure-ip-access.py').write_text('import os,sys\nfrom pathlib import Path\nPath(os.environ["GEMS_TEST_IP_RECEIPT"]).write_text(" ".join(sys.argv[1:]))\n')
 env['GEMS_TEST_IP_RECEIPT']=str(base/'ip-receipt')
 uname.write_text('#!/bin/sh\necho Linux\n')
 nginx=bin/'nginx';nginx.write_text('#!/bin/sh\nexit 0\n');nginx.chmod(0o755)
 r=subprocess.run(['bash',str(cloudkit/'deploy.sh'),'--target',str(target),'--ip','203.0.113.10'],env=env,capture_output=True,text=True)
 assert r.returncode==0,(r.stdout,r.stderr)
 assert (base/'ip-receipt').read_text()==f'{target} --ip 203.0.113.10'
 assert (target/'compose.yml').read_text()=='existing compose sentinel\n'
 assert (target/'.env').read_text()=='existing environment sentinel\n'
 assert (target/'customer-data.txt').read_text()=='existing customer fixture'
 for args in [('--ip','bad;id'),('--target','/'),('--target','/root'),('--update','--target',str(base/'missing'))]:
  before=log.read_text();r=subprocess.run(['bash',str(ROOT/'deploy.sh'),*args],env=env,capture_output=True,text=True)
  assert r.returncode!=0 and log.read_text()==before
 unknown=base/'unrecognized';unknown.mkdir();(unknown/'precious.txt').write_text('keep')
 r=subprocess.run(['bash',str(ROOT/'deploy.sh'),'--target',str(unknown)],env=env,capture_output=True,text=True)
 assert r.returncode!=0 and (unknown/'precious.txt').read_text()=='keep'
 # A failed download cannot launch a partial installer.
 curl=bin/'curl';curl.write_text('#!/bin/sh\nexit 22\n');curl.chmod(0o755)
 receipt=base/'receipt';env['GEMS_TEST_RECEIPT']=str(receipt)
 r=subprocess.run(['bash',str(ROOT/'bootstrap.sh')],env=env,capture_output=True,text=True)
 assert r.returncode==22 and not receipt.exists()
 # Test real temporary archive extraction and argument forwarding.
 payload=base/'payload';(payload/'addons/gems_pos').mkdir(parents=True)
 (payload/'addons/gems_pos/__manifest__.py').write_text("{'version':'19.0.13.0.0'}")
 (payload/'deploy.sh').write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$GEMS_TEST_RECEIPT"\n')
 archive=base/'archive.tar.gz'
 with tarfile.open(archive,'w:gz') as tar:tar.add(payload,arcname='repo-sha')
 env['GEMS_TEST_ARCHIVE']=str(archive)
 curl.write_text('''#!/usr/bin/env python3
import os,sys,shutil
args=sys.argv[1:];shutil.copyfile(os.environ['GEMS_TEST_ARCHIVE'],args[args.index('-o')+1])
''');curl.chmod(0o755)
 r=subprocess.run(['bash',str(ROOT/'bootstrap.sh'),'--target',str(target),'--ip','203.0.113.10'],env=env,capture_output=True,text=True)
 assert r.returncode==0 and receipt.read_text().strip()==f'--target {target} --ip 203.0.113.10'
print('Passed actual update branch, backup-before-update, no account/config/data reset, invalid/non-shop path rejection, failed-download stop, archive extraction and argument forwarding.')

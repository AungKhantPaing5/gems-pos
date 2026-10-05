#!/usr/bin/env python3
"""Loopback-only maintenance API. Odoo issues short-lived manager tickets."""
import base64, hashlib, hmac, json, os, re, secrets, subprocess, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT=Path(os.environ.get('GEMS_ROOT','/root/gems-pos')).resolve()
STATE=ROOT/'maintenance'
KEY=(STATE/'key').read_bytes()
JOBS=STATE/'jobs'; JOBS.mkdir(mode=0o700,exist_ok=True)
UPLOADS=STATE/'uploads'; UPLOADS.mkdir(mode=0o700,exist_ok=True)
LOCK=threading.Lock()
MAX_UPLOAD=1024*1024*1024

def verify(ticket):
    try:
        payload,sig=ticket.split('.')
        expected=hmac.new(KEY,payload.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,sig):return None
        obj=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
        if obj.get('scope')!='gems-maintenance' or not isinstance(obj.get('uid'),int) or not time.time()<obj['exp']<=time.time()+1900:return None
        return obj
    except (ValueError,KeyError,TypeError):return None

def statefile(jid):return JOBS/(jid+'.json')
def save(job):
    p=statefile(job['id']);tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(job));os.chmod(tmp,0o600);tmp.replace(p)
def load(jid):
    if not re.fullmatch('[a-f0-9]{32}',jid):raise ValueError('Invalid job')
    return json.loads(statefile(jid).read_text())

def perform(job,upload=None):
    try:
        job['status']='running';save(job)
        command=['bash',str(ROOT/'scripts'/('backup.sh' if job['kind']=='backup' else 'restore-ui.sh'))]
        command+= [str(ROOT)] if job['kind']=='backup' else [str(upload),str(ROOT),'--replace-existing']
        log=JOBS/(job['id']+'.log')
        with log.open('wb') as f:
            result=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,timeout=1800,cwd=ROOT)
        if result.returncode:raise RuntimeError('Maintenance failed. Administrator should inspect the server job log; restore failures may leave POS stopped.')
        if job['kind']=='backup':
            candidates=[line.strip() for line in log.read_text(errors='replace').splitlines() if line.startswith(str(ROOT/'backups')+'/') and line.endswith('.tar.gz')]
            if not candidates:raise RuntimeError('Backup output missing.')
            file=Path(candidates[-1]).resolve()
            if file.parent!=ROOT/'backups' or not file.is_file():raise RuntimeError('Backup file missing.')
            job['file']=str(file);job['filename']=file.name;job['size']=file.stat().st_size
        job['status']='done';job['message']='Backup ready to download.' if job['kind']=='backup' else 'Restore complete. Sign in using the accounts/passwords from the backup.'
    except Exception as e:
        job['status']='failed';job['message']=str(e)
    finally:
        save(job)
        if upload:upload.unlink(missing_ok=True)
        LOCK.release()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,obj,status=200):
        raw=json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def auth(self):
        ticket=self.headers.get('Authorization','').removeprefix('Bearer ');who=verify(ticket)
        if not who:self.reply({'error':'Manager session expired. Reopen the POS Backup tab.'},401)
        return who
    def do_GET(self):
        who=self.auth()
        if not who:return
        try:
            parts=self.path.split('/')
            if len(parts)!=4 or parts[1]!='gems-maintenance' or parts[2] not in ('jobs','download'):raise ValueError()
            job=load(parts[3])
            if job['uid']!=who['uid']:return self.reply({'error':'Access denied'},403)
            if parts[2]=='jobs':return self.reply({k:v for k,v in job.items() if k not in ('file',)})
            if job['status']!='done' or job['kind']!='backup':raise ValueError()
            p=Path(job['file']).resolve()
            if p.parent!=ROOT/'backups':raise ValueError()
            with p.open('rb') as f:
                self.send_response(200);self.send_header('Content-Type','application/gzip');self.send_header('Content-Disposition','attachment; filename="'+p.name+'"');self.send_header('Content-Length',str(p.stat().st_size));self.send_header('Cache-Control','no-store');self.end_headers()
                while chunk:=f.read(1024*1024):self.wfile.write(chunk)
        except (FileNotFoundError,ValueError,KeyError):self.reply({'error':'Job not found.'},404)
    def do_POST(self):
        who=self.auth()
        if not who:return
        kind={'/gems-maintenance/backup':'backup','/gems-maintenance/restore':'restore'}.get(self.path)
        if not kind:return self.reply({'error':'Unknown operation'},404)
        if kind=='restore' and self.headers.get('X-Restore-Confirm')!='RESTORE':return self.reply({'error':'Restore confirmation required'},400)
        try:length=int(self.headers.get('Content-Length','0'))
        except ValueError:return self.reply({'error':'Invalid upload length'},400)
        if kind=='restore' and not 0<length<=MAX_UPLOAD:return self.reply({'error':'Select a backup archive of at most 1 GiB.'},413)
        if not LOCK.acquire(blocking=False):return self.reply({'error':'Another maintenance operation is running.'},409)
        jid=secrets.token_hex(16);upload=None
        try:
            if kind=='restore':
                upload=UPLOADS/(jid+'.tar.gz')
                with upload.open('xb') as f:
                    os.chmod(upload,0o600);remaining=length
                    while remaining:
                        chunk=self.rfile.read(min(1024*1024,remaining))
                        if not chunk:raise ValueError('Upload incomplete.')
                        f.write(chunk);remaining-=len(chunk)
            job={'id':jid,'kind':kind,'uid':who['uid'],'status':'queued','created':time.time()};save(job)
            self.reply({'id':jid,'status':'queued'},202)
            threading.Timer(2,perform,args=(job,upload)).start()
        except Exception:
            if upload:upload.unlink(missing_ok=True)
            LOCK.release();self.reply({'error':'Could not queue maintenance task.'},400)

if __name__=='__main__':
    # A restart means any interrupted operation needs inspection, not automatic replay.
    for p in JOBS.glob('*.json'):
        j=json.loads(p.read_text())
        if j['status'] in ('queued','running'):
            j.update(status='failed',message='Maintenance service restarted. Inspect the server logs before retrying.');save(j)
    ThreadingHTTPServer(('127.0.0.1',8099),Handler).serve_forever()

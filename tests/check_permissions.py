"""Authorization checks against actual functions; no Odoo runtime required."""
import ast,json
from pathlib import Path
from types import SimpleNamespace as N
root=Path(__file__).resolve().parents[1]
class Fields:
 def __getattr__(self,k):return lambda *a,**kw:None
class API:
 @staticmethod
 def model_create_multi(fn):return fn
ns={'json':json,'models':N(Model=object),'fields':Fields(),'api':API(),'ValidationError':ValueError,'AccessError':PermissionError}
t=ast.parse((root/'addons/gems_pos/models/permissions.py').read_text());body=[n for n in t.body if not isinstance(n,(ast.Import,ast.ImportFrom))];exec(compile(ast.Module(body=body,type_ignores=[]),'permissions','exec'),ns)
normalize=ns['normalize_permissions'];presets=ns['permission_presets']();keys=ns['PERMISSION_LABELS'];User=ns['GemsUser']
assert presets['manager']['products_write'] and presets['manager']['barcode_print'] and not presets['manager']['stock_in_delete']
assert presets['readonly']['products_read'] and presets['readonly']['transactions_read'] and not presets['readonly']['sell']
for child,parent in ns['DEPENDENCIES'].items():assert normalize({child:True})[parent]
for invalid in [{'products_write':'false'},{'admin':True},[],{'sell':1}]:
 try:normalize(invalid);raise AssertionError()
 except ValueError:pass
class Account:
 def __init__(self,perms,uid=4,admin=False):
  self.id=uid;self.active=True;self.share=not admin;self.name='Account';self.login='account';self.gems_permissions=json.dumps(perms) if perms is not None else None;self.gems_profile='custom';self.admin=admin
 def ensure_one(self):pass
 def sudo(self):return self
 def has_group(self,k):return self.admin if k=='gems_pos.group_manager' else (k=='gems_pos.group_staff')
 def gems_effective_permissions(self):return User.gems_effective_permissions(self)
 def exists(self):return self
 def write(self,v):self.__dict__.update(v)
reader=Account(presets['readonly']);manager=Account(presets['manager']);admin=Account(None,2,True)
assert all(admin.gems_effective_permissions().values())
assert Account(None).gems_effective_permissions()==presets['staff']
corrupt=Account(None);corrupt.gems_permissions='broken';assert not any(corrupt.gems_effective_permissions().values())
# ORM permission fields cannot be modified by a delegated manager even if it has every operational permission.
proxy=N(env=N(su=False,user=manager))
try:User._check_gems_permission_write(proxy,{'gems_permissions':'{}'});raise AssertionError()
except PermissionError:pass
# Guard/require helpers and the real endpoints.
ct=ast.parse((root/'addons/gems_pos/controllers/main.py').read_text());cl=next(n for n in ct.body if isinstance(n,ast.ClassDef));functions=[n for n in cl.body if isinstance(n,ast.FunctionDef)]
for f in functions:f.decorator_list=[]
cn={'json':json,'ValidationError':ValueError,'AccessError':PermissionError,'PERMISSION_LABELS':keys,'DEPENDENCIES':ns['DEPENDENCIES'],'permission_presets':ns['permission_presets'],'normalize_permissions':normalize,'fields':N(Datetime=N(now=lambda:'now'))}
exec(compile(ast.Module(body=functions,type_ignores=[]),'controller','exec'),cn)
class Env(dict):pass
env=Env();env.user=reader;env.uid=reader.id;env.cr=N(execute=lambda *a:None)
cn['request']=N(env=env)
h=N(result=lambda x:x);h.guard=lambda admin=False:cn['guard'](h,admin);h.require=lambda k:cn['require'](h,k);h.delete_permission=lambda kind:cn['delete_permission'](h,kind)
# Each endpoint must reject missing permission before looking up business records.
def denied(endpoint,*args,**kw):
 try:cn[endpoint](h,*args,**kw);raise AssertionError(endpoint+' was allowed')
 except PermissionError:pass
for name,args in [('add',()),('edit_item',(1,)),('restock',(1,1)),('stock_reduce',(1,1,'reason','a'*32)),('sale',()),('stockin_labels',('[1]',)),('product_label',(1,)),('staff_list',()),('staff_create',()),('staff_permissions',(4,'{}')),('maintenance_ticket',())]:denied(name,*args)
for kind in ['item','in','out','transactions']:
 denied('delete',kind,1);denied('delete_selected',kind,'[1]')
# Product writers cannot smuggle a stock change or nonzero opening stock without stock_adjust.
writer=Account(normalize({'products_write':True}));env.user=writer
cn['math']=__import__('math');cn['re']=__import__('re')
for args in [dict(name='Ruby',code='R1',price='100',quantity='1')]:denied('add',**args)
for kind in ['item','in','out','transactions']:denied('delete',kind,1)
# Manager preset can read Stock In and request labels, but cannot delete/cancel accounts or history.
env.user=manager
h.require('products_write');h.require('stock_adjust');h.require('barcode_print');h.require('stock_in_read')
for kind in ['item','in','out','transactions']:denied('delete',kind,1);denied('delete_selected',kind,'[1]')
denied('staff_permissions',4,'{}');denied('staff_create');denied('maintenance_ticket')
# A same-session change is effective on the next request.
manager.gems_permissions=json.dumps(presets['readonly']);denied('restock',1,1)
# Protected admin and self accounts cannot be edited via account-permissions API.
class Model:
 def __init__(self,u):self.u=u
 def sudo(self):return self
 def browse(self,id):return self.u
for target in [admin]:
 env.user=admin;env.uid=admin.id;env['res.users']=Model(target);denied('staff_permissions',target.id,'{}')
# Save another account's custom permissions; no group_manager grant occurs.
target=Account(presets['staff'],uid=8);env['res.users']=Model(target)
res=cn['staff_permissions'](h,8,json.dumps({'products_read':True,'stock_in_read':True,'barcode_print':True}),'custom')
assert res['ok'] and not target.has_group('gems_pos.group_manager') and target.gems_permissions_updated_by==2
assert target.gems_effective_permissions()['barcode_print'] and not target.gems_effective_permissions()['products_write']
# A user with transactions-delete but no all-staff scope cannot cancel another seller's sale.
scoped=Account(normalize({'transactions_delete':True}));env.user=scoped;env.uid=scoped.id
v=N(cancelled=False,staff_id=N(id=99),exists=lambda:None)
v.exists=lambda:v;env['gems.voucher']=Model(v)
denied('delete','transactions',1)
print('Passed permission presets/dependencies, fail-closed validation, ORM self-escalation denial, all write/delete/admin endpoint denials, manager print-without-delete, next-request revocation, protected admin, audited account update and own-voucher cancellation scope.')

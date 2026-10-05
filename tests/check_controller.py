"""Isolated controller checks; does not substitute for live Odoo tests."""
import ast,json,math,re
from pathlib import Path
from types import SimpleNamespace as N
from decimal import Decimal,ROUND_HALF_UP
root=Path(__file__).resolve().parents[1]
tree=ast.parse((root/'addons/gems_pos/controllers/main.py').read_text())
cl=next(n for n in tree.body if isinstance(n,ast.ClassDef))
functions=[n for n in cl.body if isinstance(n,ast.FunctionDef) and n.name in ('delete_selected','delete','scan','edit_item','stockin_labels')]
for f in functions:f.decorator_list=[]
money=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='money')
class Rows(list):
 @property
 def ids(self):return [r.id for r in self]
 @property
 def item_id(self):return Rows([r.item_id for r in self])
 @property
 def line_ids(self):return Rows([l for r in self for l in r.line_ids])
 def exists(self):return self
 def write(self,v):
  for r in self:r.write(v)
class Item:
 def __init__(self,id,q):self.id=id;self.code='ITEM'+str(id);self.quantity=q;self.active=True;self.image=False
 def exists(self):return self
 def invalidate_recordset(self,*a):pass
 def write(self,v):self.__dict__.update(v)
class Voucher(Item):
 def __init__(self,id,item):super().__init__(id,0);self.cancelled=False;self.line_ids=Rows([N(item_id=item,quantity=3)])
class Model:
 def __init__(self,rows):self.rows={r.id:r for r in rows}
 def sudo(self):return self
 def browse(self,ids):return Rows([self.rows[i] for i in ids if i in self.rows]) if isinstance(ids,list) else self.rows.get(ids)
 def search(self,domain,limit=None):
  if domain[0][0]=='code':return next((r for r in self.rows.values() if r.active and r.code==domain[0][2]),False)
  if domain[0][0]=='adjustment_token':return False
  return Rows([])
 def create(self,v):created.append(v)
class Env(dict):pass
items=[Item(1,10),Item(2,20)];vouchers=[Voucher(8,items[0]),Voucher(9,items[1])]
movements=[N(id=5,kind='in'),N(id=6,kind='out')]
for r in movements:r.exists=lambda r=r:r
for r in movements:r.write=lambda v,r=r:r.__dict__.update(v)
created=[];locks=[]
env=Env({'gems.item':Model(items),'gems.voucher':Model(vouchers),'gems.movement':Model(movements)});env.uid=2;env.user=N(gems_effective_permissions=lambda:{'transactions_all':True});env.cr=N(execute=lambda sql,args:locks.append((sql,args)))
ns={'request':N(env=env,httprequest=N(files={})), 'json':json,'math':math,'re':re,'Decimal':Decimal,'ROUND_HALF_UP':ROUND_HALF_UP,'ValidationError':ValueError,'AccessError':PermissionError,'fields':N(Datetime=N(now=lambda:'now'))}
exec(compile(ast.Module(body=[money,*functions],type_ignores=[]),'controller','exec'),ns)
h=N(cost_values=lambda kw:{},guard=lambda a=True:None,require=lambda key:None,delete_permission=lambda kind:None,result=lambda d:d,move=lambda i,k,q,v:created.append((i.id,k,q)))
h.delete=lambda k,id:ns['delete'](h,k,id)
bulk=ns['delete_selected'];bulk(h,'transactions','[9,8,9]')
assert [i.quantity for i in items]==[13,23] and all(v.cancelled for v in vouchers)
assert locks[0][1]==[[8,9]] and locks[1][1]==[[1,2]]
bulk(h,'transactions','[8,9]');assert [i.quantity for i in items]==[13,23]
bulk(h,'in','[5]');assert movements[0].hidden and items[0].quantity==13
for kind,ids in [('in','[6]'),('out','[999]'),('item','[1]'),('in','[]'),('in','[true]'),('in','[1.2]'),('in','bad'),('in',json.dumps(list(range(1,62))))]:
 try:bulk(h,kind,ids);raise AssertionError((kind,ids))
 except ValueError:pass
items[0].code='R001';items[0].name='မြန်မာပတ္တမြား';items[0].price=100;items[0].team='A'
assert ns['scan'](h,'R001')['item']['id']==1
assert ns['scan'](h,'absent')['item'] is None
items[0].active=False;assert ns['scan'](h,'R001')['item'] is None;items[0].active=True
f=ns['edit_item'];d={'name':'မြန်မာပတ္တမြား','code':'R001','barcode':'ignored','team':'A','price':'100','quantity':'1','expected_quantity':'13','token':'a'*32}
f(h,1,**d);assert items[0].quantity==1 and items[0].barcode=='R001' and created[-1]['quantity']==12
h.guard=lambda a=True:(_ for _ in ()).throw(PermissionError());h.require=lambda key:h.guard();h.delete_permission=lambda kind:h.guard()
try:bulk(h,'in','[5]');raise AssertionError()
except PermissionError:pass
for p in root.rglob('*.py'):ast.parse(p.read_text())
from lxml import etree
for p in root.rglob('*.xml'):etree.parse(str(p))
print('Passed bulk cancellation, retry returns stock once, history hide leaves stock, batch locks sorted, selection validation, exact scan/archived exclusions, unified edit, staff denial, Python/XML syntax.')
# Verify barcode merge even when old barcode values are another product's code.
import sqlite3,runpy
con=sqlite3.connect(':memory:');con.execute('CREATE TABLE gems_item (id INTEGER PRIMARY KEY, code TEXT UNIQUE, barcode TEXT UNIQUE)')
con.executemany('INSERT INTO gems_item VALUES (?,?,?)',[(1,'A','B'),(2,'B','A'),(3,'OLD','LEGACY')])
class Cursor:
 def execute(self,sql,args=()):
  if sql.startswith('LOCK TABLE'):return
  con.execute(sql.replace('%s','?').replace('id::text','CAST(id AS TEXT)'),args)
runpy.run_path(str(root/'addons/gems_pos/migrations/19.0.10.0.0/post-migration.py'))['migrate'](Cursor(),'19.0.9.0.0')
assert con.execute('SELECT code,barcode FROM gems_item ORDER BY id').fetchall()==[('A','A'),('B','B'),('OLD','OLD')]
print('Passed existing barcode migration with swapped legacy values and unique constraints.')

# Labels group multiple selected receipts by current active product, without stock mutation.
h.guard=lambda a=True:None;h.require=lambda key:None;h.delete_permission=lambda kind:None
items[0].name='မြန်မာပတ္တမြား';items[0].code='CURRENT';items[1].name='Pearl';items[1].code='P001'
movements=[N(id=21,kind='in',hidden=False,item_id=items[0],quantity=2),N(id=22,kind='in',hidden=False,item_id=items[0],quantity=3),N(id=23,kind='in',hidden=False,item_id=items[1],quantity=4)]
env['gems.movement']=Model(movements)
before=[i.quantity for i in items]
f=ns['stockin_labels'];labels=f(h,'[21,22,23,21]')['items']
assert len(labels)==2 and labels[0]['received']==5 and labels[0]['code']=='CURRENT'
assert [i.quantity for i in items]==before
movements[0].hidden=True
try:f(h,'[21]');raise AssertionError()
except ValueError:pass
movements[0].hidden=False;items[0].active=False
try:f(h,'[21]');raise AssertionError()
except ValueError:pass
items[0].active=True;movements[0].kind='out'
try:f(h,'[21]');raise AssertionError()
except ValueError:pass
h.guard=lambda a=True:(_ for _ in ()).throw(PermissionError());h.require=lambda key:h.guard();h.delete_permission=lambda kind:h.guard()
try:f(h,'[23]');raise AssertionError()
except PermissionError:pass
print('Passed selected Stock In labels grouping/current-code lookup, stock preservation, hidden/out/archived rejection and manager-only access.')

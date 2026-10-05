"""Offline calculations, Excel interoperability and actual controller security checks."""
import ast, importlib.util, json, math, re
from pathlib import Path
from types import SimpleNamespace as N
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from datetime import date
from zipfile import ZipFile
from lxml import etree
from openpyxl import load_workbook
ROOT=Path(__file__).resolve().parents[1]
C=ROOT/'addons/gems_pos/controllers'
spec=importlib.util.spec_from_file_location('report_tools',C/'report_tools.py');t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
a,b,ds,de=t.period_bounds('2026','1');assert str(a)=='2025-12-31 17:30:00' and str(b)=='2026-01-31 17:30:00'
assert t.period_bounds(2026,0)[3]==date(2027,1,1)
assert t.period_bounds(2026,12)[1]==t.period_bounds(2026,0)[1]
for y,m in [(1999,1),(2101,1),(2026,13),('2026 OR 1=1',0),(2026,-1),(2026,'nan')]:
 try:t.period_bounds(y,m);raise AssertionError('accepted invalid period')
 except ValueError:pass
r=t.assemble_report(2026,0,[dict(period='2026-01',stock_in=100,stock_out=12,sold_quantity=10,sales_count=2,revenue=900,discount=100,cost=600,missing_cost_quantity=0,expenses=400),dict(period='2026-02',revenue=100,cost=0,missing_cost_quantity=1)])
assert len(r['rows'])==12 and r['rows'][0]['gross_profit']==300 and r['rows'][0]['net_profit']==-100
assert r['rows'][1]['net_profit'] is None and r['total']['gross_profit'] is None
assert r['rows'][2]['net_profit']==0
xlsx=t.excel_bytes(r)
with ZipFile(BytesIO(xlsx)) as z:
 for name in z.namelist():etree.fromstring(z.read(name))
w=load_workbook(BytesIO(xlsx),data_only=True);s=w.active
assert s['F2'].value==1000 and s['L2'].value=='Cost missing' and s['L3'].value==-100 and s['L4'].value=='Cost missing'
assert s.freeze_panes=='A2' and s['F2'].number_format=='#,##0.00'
# Compile the actual report controller with only decorators/bases removed.
tree=ast.parse((C/'reports.py').read_text());cl=next(x for x in tree.body if isinstance(x,ast.ClassDef));cl.bases=[]
for f in cl.body:
 if isinstance(f,ast.FunctionDef):f.decorator_list=[]
class Env(dict):
 def flush_all(self):pass
class Cr:
 def execute(self,*args):self.last=args
 def dictfetchall(self):return []
class Model:
 def __init__(self):self.values=[];self.row=False
 def sudo(self):return self
 def search(self,*a,**kw):return self.row
 def create(self,v):self.values.append(v)
 def browse(self,id):return N(exists=lambda:self.row)
env=Env();env.uid=1;env.cr=Cr();env.user=N(active=True,has_group=lambda x:False)
ns=dict(request=N(env=env,make_response=lambda data,headers:(data,headers),make_json_response=lambda d:d),AccessError=PermissionError,ValidationError=ValueError,re=re,math=math,date=date,fields=N(Datetime=N(now=lambda:'now')),period_bounds=t.period_bounds,assemble_report=t.assemble_report,excel_bytes=t.excel_bytes,HEADERS=t.HEADERS,report_values=t.report_values,money=t.money)
from html import escape
ns['escape']=escape
sql=next(x for x in tree.body if isinstance(x,ast.Assign) and any(isinstance(z,ast.Name) and z.id=='REPORT_SQL' for z in x.targets));ns['REPORT_SQL']=ast.literal_eval(sql.value)
assert "COALESCE(v.cancelled,false)=false" in ns['REPORT_SQL'] and 'hidden' not in ns['REPORT_SQL']
assert "AT TIME ZONE 'Asia/Yangon'" in ns['REPORT_SQL'] and 'LEFT JOIN LATERAL' in ns['REPORT_SQL']
exec(compile(ast.Module(body=[cl],type_ignores=[]),'reports','exec'),ns);h=ns['GemsReports']()
for name,args in [('report',(2026,)),('excel',(2026,)),('pdf',(2026,)),('expense',('2026-01-01','Rent','50','a'*32)),('void_expense',(1,))]:
 try:getattr(h,name)(*args);raise AssertionError('staff accessed '+name)
 except PermissionError:pass
env.user.has_group=lambda x:True
assert h.data(2026,1)['total']['net_profit']==0
assert h.excel(2026,1)[0][:2]==b'PK' and 'Save as PDF' in h.pdf(2026,1)[0]
env['gems.expense']=m=Model()
h.expense('2026-01-01','Rent','50','a'*32);assert m.values[0]['amount']==50
for amount in ['nan','inf','-1','0','bad','0.001']:
 try:h.expense('2026-01-01','Rent',amount,'a'*32);raise AssertionError('bad expense')
 except ValueError:pass
m.row=N(staff_id=N(id=1));assert h.expense('2026-01-01','Rent','50','a'*32)['duplicate'] and len(m.values)==1
m.row.staff_id.id=2
try:h.expense('2026-01-01','Rent','50','a'*32);raise AssertionError('stolen token')
except PermissionError:pass
# Actual cost helper and actual sale snapshot, not a duplicate implementation.
tree=ast.parse((C/'main.py').read_text());cl=next(x for x in tree.body if isinstance(x,ast.ClassDef));funcs=[f for f in cl.body if isinstance(f,ast.FunctionDef) and f.name in ('cost_values','sale')]
for f in funcs:f.decorator_list=[]
ns.update(json=json,Decimal=Decimal,ROUND_HALF_UP=ROUND_HALF_UP)
exec(compile(ast.Module(body=funcs,type_ignores=[]),'main','exec'),ns)
handler=N(guard=lambda admin:None,require=lambda p:None,result=lambda x:x,move=lambda *a:None)
assert ns['cost_values'](handler,{'cost_price':''})=={'cost_price':0,'cost_known':False}
assert ns['cost_values'](handler,{'cost_price':'0'})=={'cost_price':0,'cost_known':True}
for value in ('nan','inf','-2','bad'):
 try:ns['cost_values'](handler,{'cost_price':value});raise AssertionError('invalid cost')
 except ValueError:pass
handler.guard=lambda admin:(_ for _ in ()).throw(PermissionError())
try:ns['cost_values'](handler,{'cost_price':'50'});raise AssertionError('staff changed cost')
except PermissionError:pass
class Items(list):
 def exists(self):return self
 def invalidate_recordset(self):pass
item=N(id=1,active=True,quantity=5,name='မြန်မာပတ္တမြား',code='R1',price=100,cost_price=20,cost_known=True)
class ItemModel:
 def sudo(self):return self
 def browse(self,ids):return Items([item])
class Vouchers(Model):
 def create(self,v):self.values.append(v);return N(id=1,name='V1')
vm=Vouchers();env.update({'gems.voucher':vm,'gems.item':ItemModel(),'ir.sequence':N(sudo=lambda:N(next_by_code=lambda code:'V1'))})
ns['sale'](handler,token='b'*32,customer='Test',discount=10,payment_method='Cash',lines=json.dumps([dict(id=1,qty=2)]))
v=vm.values[0];line=v['line_ids'][0][2]
assert v['total']==180 and line['cost_price']==20 and line['cost_known'] and item.quantity==3
item.cost_price=999;assert line['cost_price']==20
print('Passed Myanmar month/year boundaries, missing-cost and loss calculations, valid XLSX/readback/number formats, report/export/expense admin guards, expense validation/retries, cost guards, sale-time cost snapshots and price-change stability.')

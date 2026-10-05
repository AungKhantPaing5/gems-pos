import re, math
from datetime import date
from html import escape
from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError
from .report_tools import period_bounds, assemble_report, excel_bytes, HEADERS, report_values, money

# One aggregate query: avoids inconsistent totals or fetching the entire ledger.
REPORT_SQL='''
WITH entries AS (
 SELECT to_char(m.create_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Yangon','YYYY-MM') AS period,
   COALESCE(SUM(m.quantity) FILTER (WHERE m.kind='in'),0) AS stock_in,
   COALESCE(SUM(m.quantity) FILTER (WHERE m.kind='out'),0) AS stock_out,
   0 AS sold_quantity, 0 AS sales_count, 0 AS revenue, 0 AS discount, 0 AS cost, 0 AS missing_cost_quantity, 0 AS expenses
 FROM gems_movement m WHERE m.create_date >= %(start)s AND m.create_date < %(end)s GROUP BY 1
 UNION ALL
 SELECT to_char(v.create_date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Yangon','YYYY-MM'),
   0,0,SUM(COALESCE(l.qty,0)),COUNT(*),SUM(v.total),SUM(v.discount),SUM(COALESCE(l.cost,0)),SUM(COALESCE(l.missing,0)),0
 FROM gems_voucher v
 LEFT JOIN LATERAL (SELECT SUM(quantity) AS qty,
   SUM(CASE WHEN cost_known THEN ROUND(cost_price::numeric * quantity,2) ELSE 0 END) AS cost,
   SUM(CASE WHEN COALESCE(cost_known,false) THEN 0 ELSE quantity END) AS missing
   FROM gems_line WHERE voucher_id=v.id) l ON true
 WHERE COALESCE(v.cancelled,false)=false AND v.create_date >= %(start)s AND v.create_date < %(end)s GROUP BY 1
 UNION ALL
 SELECT to_char(e.date,'YYYY-MM'),0,0,0,0,0,0,0,0,SUM(e.amount)
 FROM gems_expense e WHERE COALESCE(e.voided,false)=false AND e.date >= %(date_start)s AND e.date < %(date_end)s GROUP BY 1
)
SELECT period, SUM(stock_in) AS stock_in,SUM(stock_out) AS stock_out,SUM(sold_quantity) AS sold_quantity,
 SUM(sales_count) AS sales_count,SUM(revenue) AS revenue,SUM(discount) AS discount,SUM(cost) AS cost,
 SUM(missing_cost_quantity) AS missing_cost_quantity,SUM(expenses) AS expenses FROM entries GROUP BY period ORDER BY period
'''

class GemsReports(http.Controller):
    def guard(self):
        u=request.env.user
        if not u.active or not u.has_group('gems_pos.group_manager'):
            raise AccessError('Administrator report access required.')

    def data(self,year,month):
        self.guard()
        try:start,end,ds,de=period_bounds(year,month)
        except ValueError as exc:raise ValidationError(str(exc))
        # Flush pending ORM writes before reading SQL aggregates.
        request.env.flush_all()
        request.env.cr.execute(REPORT_SQL,dict(start=start,end=end,date_start=ds,date_end=de))
        return assemble_report(year,month,request.env.cr.dictfetchall())

    @http.route('/gems/api/reports',type='http',auth='user',methods=['GET'])
    def report(self,year,month='0',**kw):
        data=self.data(year,month)
        _,_,ds,de=period_bounds(year,month)
        expenses=request.env['gems.expense'].sudo().search([('date','>=',ds),('date','<',de),('voided','=',False)],limit=60)
        data['expense_rows']=[dict(id=e.id,date=str(e.date),name=e.name,amount=e.amount,staff=e.staff_id.name) for e in expenses]
        data['expense_list_limit']=60
        return request.make_json_response(data)

    @http.route('/gems/reports/excel',type='http',auth='user',methods=['GET'])
    def excel(self,year,month='0',**kw):
        report=self.data(year,month)
        return request.make_response(excel_bytes(report),[
            ('Content-Type','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition',f'attachment; filename="gems-report-{report["period"].replace(" ","-")}.xlsx"'),
            ('Cache-Control','no-store')])

    @http.route('/gems/reports/pdf',type='http',auth='user',methods=['GET'])
    def pdf(self,year,month='0',**kw):
        r=self.data(year,month)
        def cell(value):
            if value is None:return 'Cost missing'
            if isinstance(value,float):return format(value,',.2f')
            return escape(str(value))
        heads=''.join('<th>'+escape(h)+'</th>' for h in HEADERS)
        rows=''.join('<tr>'+''.join('<td>'+cell(v)+'</td>' for v in report_values(row))+'</tr>' for row in [r['total'],*r['rows']])
        html='''<!doctype html><html><head><meta charset="utf-8"><title>Gems report '''+escape(r['period'])+'''</title><style>
        @font-face{font-family:Myanmar;src:url('/gems_pos/static/src/fonts/NotoSansMyanmar-Regular.ttf')}
        body{font-family:Arial,Myanmar,sans-serif;color:#123d34;padding:16px}table{border-collapse:collapse;width:100%;font-size:10px}td,th{padding:7px;border:1px solid #ddd;text-align:right}th{background:#edf2ef}td:first-child{text-align:left}tbody tr:first-child{font-weight:bold}p{font-size:12px}button{padding:10px} @page{size:A4 landscape;margin:12mm}@media print{button{display:none}body{padding:0}thead{display:table-header-group}tr{break-inside:avoid}}
        </style></head><body><button onclick="window.print()">Print / Save as PDF</button><h1>GEMS — Stock &amp; profit report</h1><p>Period: '''+escape(r['period'])+''' · Myanmar time · Currency: MMK</p><table><thead><tr>'''+heads+'''</tr></thead><tbody>'''+rows+'''</tbody></table><p>Gross profit = sales after discount − recorded cost of goods sold.<br>Net profit / loss = gross profit − recorded operating expenses.</p><p>Profit is unavailable for periods with sales without recorded cost. Changing product cost only affects future sales. Stock counts include corrections, returns and hidden ledger rows. Cancelled sales are excluded from revenue. This is an operating report using recorded costs and expenses; stock corrections are not booked as expenses automatically.</p><script>document.fonts.ready.then(()=>window.print());</script></body></html>'''
        return request.make_response(html,[('Content-Type','text/html; charset=utf-8'),('Cache-Control','no-store')])

    @http.route('/gems/api/expense',type='http',auth='user',methods=['POST'])
    def expense(self,date_value,name,amount,token,**kw):
        self.guard()
        try:d=date.fromisoformat(date_value);a=float(amount)
        except (TypeError,ValueError):raise ValidationError('Valid expense date and amount required.')
        name=name.strip()
        if not 2000<=d.year<=2100 or not name or len(name)>200 or not math.isfinite(a) or not 0<a<=999999999999 or money(a)<=0:
            raise ValidationError('Name and positive expense amount required.')
        if not re.fullmatch(r'[a-f0-9]{32}',token):raise ValidationError('Invalid expense token.')
        request.env.cr.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',['gems-expense:'+token])
        model=request.env['gems.expense'].sudo()
        existing=model.search([('token','=',token)],limit=1)
        if existing:
            if existing.staff_id.id!=request.env.uid:raise AccessError('Invalid expense token owner.')
            return request.make_json_response({'ok':True,'duplicate':True})
        model.create(dict(date=d,name=name,amount=money(a),token=token,staff_id=request.env.uid))
        return request.make_json_response({'ok':True})

    @http.route('/gems/api/expense/void',type='http',auth='user',methods=['POST'])
    def void_expense(self,record_id,**kw):
        self.guard()
        row=request.env['gems.expense'].sudo().browse(int(record_id)).exists()
        if not row:raise ValidationError('Expense missing.')
        row.write(dict(voided=True,voided_by=request.env.uid,voided_at=fields.Datetime.now()))
        return request.make_json_response({'ok':True})

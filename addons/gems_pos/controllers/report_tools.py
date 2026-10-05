"""Pure report and Excel helpers; no Odoo dependency."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
import re

ZONE=ZoneInfo('Asia/Yangon')
METRICS=('stock_in','stock_out','sold_quantity','sales_count','revenue','discount','cost','missing_cost_quantity','expenses')
HEADERS=('Period','Stock In units','Stock Out units','Sold units','Vouchers','Sales after discount (MMK)','Discount (MMK)','Known cost of sales (MMK)','Units without cost','Expenses (MMK)','Gross profit (MMK)','Net profit / loss (MMK)')

def period_bounds(year, month=0):
    if not re.fullmatch(r'[0-9]{4}',str(year)) or not re.fullmatch(r'[0-9]{1,2}',str(month)):
        raise ValueError('Invalid report period.')
    year,month=int(year),int(month)
    if not 2000<=year<=2100 or not 0<=month<=12:raise ValueError('Use a year from 2000 to 2100 and month 0 to 12.')
    start=datetime(year,month or 1,1,tzinfo=ZONE)
    end=datetime(year+1,1,1,tzinfo=ZONE) if not month or month==12 else datetime(year,month+1,1,tzinfo=ZONE)
    return start.astimezone(timezone.utc).replace(tzinfo=None),end.astimezone(timezone.utc).replace(tzinfo=None),start.date(),end.date()

def money(value):return float(Decimal(str(value or 0)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))

def assemble_report(year, month, records):
    year,month=int(year),int(month)
    rows={f'{year:04d}-{m:02d}':dict(period=f'{year:04d}-{m:02d}',**dict.fromkeys(METRICS,0)) for m in ([month] if month else range(1,13))}
    for rec in records:
        if rec['period'] not in rows:continue
        r=rows[rec['period']]
        for key in METRICS:r[key]+=rec.get(key) or 0
    total=dict(period=f'{year:04d}'+(f'-{month:02d}' if month else ' total'),**{key:sum(r[key] for r in rows.values()) for key in METRICS})
    for r in [*rows.values(),total]:
        for key in ('revenue','discount','cost','expenses'):r[key]=money(r[key])
        for key in ('stock_in','stock_out','sold_quantity','sales_count','missing_cost_quantity'):r[key]=int(r[key])
        r['gross_profit']=None if r['missing_cost_quantity'] else money(Decimal(str(r['revenue']))-Decimal(str(r['cost'])))
        r['net_profit']=None if r['gross_profit'] is None else money(Decimal(str(r['gross_profit']))-Decimal(str(r['expenses'])))
    return dict(year=year,month=month,period=total['period'],timezone='Asia/Yangon',rows=list(rows.values()),total=total)

def report_values(r):return [r['period'],*[r[k] for k in METRICS],r['gross_profit'],r['net_profit']]

def excel_bytes(report):
    # Inline strings prevent formula execution even when user text starts with '='.
    data=[list(HEADERS),report_values(report['total']),*[report_values(r) for r in report['rows']],[],['Amounts in MMK; dates in Myanmar time.'],['Gross = sales after discount - recorded cost. Net = gross - recorded operating expenses.'],['Cost missing means profit is unavailable; historical cost is not backfilled.'],['Stock counts include corrections, returns and hidden ledger records. Cancelled sales are excluded from revenue.']]
    def col(n):
        text=''
        while n:n,r=divmod(n-1,26);text=chr(65+r)+text
        return text
    rows=[]
    for rownum,values in enumerate(data,1):
        cells=[]
        for n,value in enumerate(values,1):
            ref=col(n)+str(rownum);style='1' if rownum==1 else '2' if n in (6,7,8,10,11,12) and isinstance(value,(int,float)) else '0'
            if value is None:value='Cost missing'
            if isinstance(value,(int,float)):
                cells.append(f'<c r="{ref}" s="{style}"><v>{value}</v></c>')
            else:
                value=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',str(value))
                cells.append(f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>')
        rows.append(f'<row r="{rownum}">'+''.join(cells)+'</row>')
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    sheet=f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{ns}"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="12" width="22" customWidth="1"/></cols><sheetData>'+''.join(rows)+'</sheetData></worksheet>'
    styles=f'<styleSheet xmlns="{ns}"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="3"><xf xfId="0"/><xf fontId="1" applyFont="1" xfId="0"/><xf numFmtId="4" applyNumberFormat="1" xfId="0"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
    out=BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Gems report" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml',sheet);z.writestr('xl/styles.xml',styles)
    return out.getvalue()

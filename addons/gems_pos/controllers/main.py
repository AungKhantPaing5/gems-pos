import json, math, base64, re
from io import BytesIO
from PIL import Image
from decimal import Decimal, ROUND_HALF_UP
from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessError, ValidationError
from ..models.permissions import PERMISSION_LABELS, DEPENDENCIES, permission_presets, normalize_permissions

def money(v):
    return float(Decimal(str(v)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))

class Gems(http.Controller):
    def guard(self, admin=False):
        u = request.env.user
        if not u.active:
            raise AccessError('This staff account has been disabled.')
        if not (u.has_group('gems_pos.group_manager') or (not admin and u.has_group('gems_pos.group_staff'))):
            raise AccessError('Gems access required.')
    def require(self, permission):
        self.guard()
        if not request.env.user.gems_effective_permissions().get(permission):
            raise AccessError('Permission denied: '+PERMISSION_LABELS.get(permission,permission))

    def delete_permission(self, kind):
        key={'item':'products_delete','in':'stock_in_delete','out':'stock_out_delete',
             'transactions':'transactions_delete'}.get(kind)
        if not key:raise ValidationError('Unknown delete action.')
        self.require(key)

    @http.route('/gems/api/session', type='http', auth='user', methods=['GET'])
    def session(self, **kw):
        self.guard()
        u=request.env.user;admin=u.has_group('gems_pos.group_manager')
        return self.result({'admin':admin,'user':u.name,'permissions':u.gems_effective_permissions(),
            'profile':'administrator' if admin else (u.sudo().gems_profile or 'staff'),
            'permission_labels':PERMISSION_LABELS,'dependencies':DEPENDENCIES,'presets':permission_presets()})

    def result(self, data):
        return request.make_json_response(data)
    @http.route(['/gems', '/gems/admin', '/gems/staff'], type='http', auth='user')
    def app(self, **kw):
        self.guard()
        return request.render('gems_pos.app')
    @http.route('/gems/api/items', type='http', auth='user', methods=['GET'])
    def items(self, q='', page='0', **kw):
        self.require('products_read')
        domain = ['|','|',('name','ilike',q[:100]),('code','ilike',q[:100]),('barcode','ilike',q[:100])] if q else []
        model=request.env['gems.item'].sudo()
        rows = model.search(domain, limit=60, offset=max(0,int(page))*60)
        if q and int(page)==0:
            exact=model.search([('code','=',q)],limit=1)
            if exact:rows=(exact | rows)[:60]
        return self.result({'admin':request.env.user.has_group('gems_pos.group_manager'), 'user':request.env.user.name, 'items':[{'id':i.id,'name':i.name,'code':i.code,'barcode':i.barcode,'team':i.team or '', 'price':i.price,'quantity':i.quantity,'image':bool(i.image),'image_version':str(i.write_date), **({'cost_price':i.cost_price,'cost_known':i.cost_known} if request.env.user.has_group('gems_pos.group_manager') else {})} for i in rows]})
    @http.route('/gems/image/<int:item_id>', type='http', auth='user', methods=['GET'])
    def image(self, item_id, **kw):
        self.require('products_read')
        i=request.env['gems.item'].sudo().browse(item_id).exists()
        if not i or not i.image: return request.not_found()
        data=base64.b64decode(i.image)
        mime=Image.MIME.get(Image.open(BytesIO(data)).format, 'application/octet-stream')
        return request.make_response(data, [('Content-Type',mime),('Cache-Control','private, max-age=300')])
    @http.route('/gems/api/item', type='http', auth='user', methods=['POST'])
    def add(self, **kw):
        self.require('products_write')
        name=kw.get('name','').strip(); code=kw.get('code','').strip(); barcode=code
        qty=int(kw.get('quantity',0)); price=float(kw.get('price',0))
        if not name or not code or not barcode or qty<0 or not math.isfinite(price) or price<0:
            raise ValidationError('Name, code, barcode, non-negative stock and valid price required.')
        if not re.fullmatch(r'[!-~]{1,32}',code):raise ValidationError('Item code: 1–32 English letters, numbers or symbols, without spaces.')
        if qty:self.require('stock_adjust')
        vals=dict(name=name,code=code,barcode=barcode,team=kw.get('team',''),price=money(price),quantity=qty)
        vals.update(self.cost_values(kw))
        f=request.httprequest.files.get('image')
        if f:
            data=f.read(3*1024*1024+1)
            if len(data)>3*1024*1024: raise ValidationError('Image maximum 3 MB.')
            vals['image']=base64.b64encode(data)
        item=request.env['gems.item'].sudo().create(vals)
        if qty:self.move(item,'in',qty)
        return self.result({'ok':True})
    def move(self,i,kind,qty,v=None):
        request.env['gems.movement'].sudo().create(dict(item_id=i.id,code=i.code,name=i.name,kind=kind,quantity=qty,staff_id=request.env.uid,customer=v.customer if v else '',voucher_id=v.id if v else False))
    @http.route('/gems/api/restock', type='http', auth='user', methods=['POST'])
    def restock(self,item_id,quantity,**kw):
        self.require('stock_adjust'); qty=int(quantity); iid=int(item_id)
        if qty<1: raise ValidationError('Quantity must be positive.')
        request.env.cr.execute('SELECT id FROM gems_item WHERE id=%s FOR UPDATE',[iid])
        i=request.env['gems.item'].sudo().browse(iid).exists()
        if not i or not i.active: raise ValidationError('Item unavailable.')
        i.invalidate_recordset(['quantity']); i.quantity+=qty; self.move(i,'in',qty)
        return self.result({'ok':True})
    @http.route('/gems/api/sale', type='http', auth='user', methods=['POST'])
    def sale(self, **kw):
        self.require('sell')
        token=kw.get('token','')
        if len(token)<16 or len(token)>100: raise ValidationError('Invalid sale token.')
        request.env.cr.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',[token])
        existing=request.env['gems.voucher'].sudo().search([('token','=',token)],limit=1)
        if existing:
            if existing.staff_id.id!=request.env.uid: raise AccessError('Invalid token owner.')
            return self.result({'id':existing.id,'name':existing.name})
        customer=kw.get('customer','').strip(); pct=float(kw.get('discount',0))
        if not customer or not math.isfinite(pct) or not 0<=pct<=100: raise ValidationError('Customer and discount 0–100 required.')
        payment=kw.get('payment_method','').strip()
        if not payment or len(payment)>128: raise ValidationError('Payment method is required (maximum 128 characters).')
        rows=json.loads(kw.get('lines','[]')); quantities={}
        if not rows or len(rows)>200: raise ValidationError('Invalid cart.')
        for row in rows:
            iid=int(row['id']); qty=int(row['qty'])
            if qty<1 or qty!=row['qty']: raise ValidationError('Use positive whole quantities.')
            quantities[iid]=quantities.get(iid,0)+qty
        ids=sorted(quantities)
        request.env.cr.execute('SELECT id FROM gems_item WHERE id = ANY(%s) ORDER BY id FOR UPDATE',[ids])
        items=request.env['gems.item'].sudo().browse(ids).exists(); items.invalidate_recordset()
        if len(items)!=len(ids): raise ValidationError('Item missing.')
        lines=[]
        for i in items:
            qty=quantities[i.id]
            if not i.active or i.quantity<qty: raise ValidationError('Not enough stock: '+i.name)
            lines.append((0,0,dict(item_id=i.id,code=i.code,name=i.name,quantity=qty,price=i.price,cost_price=i.cost_price,cost_known=i.cost_known,amount=money(Decimal(str(i.price))*qty))))
        subtotal=money(sum(Decimal(str(v[2]['amount'])) for v in lines)); pct=money(pct); discount=money(Decimal(str(subtotal))*Decimal(str(pct))/100)
        v=request.env['gems.voucher'].sudo().create(dict(name=request.env['ir.sequence'].sudo().next_by_code('gems.voucher'),token=token,payment_method=payment,customer=customer,phone=kw.get('phone',''),address=kw.get('address',''),staff_id=request.env.uid,discount_percent=pct,subtotal=subtotal,discount=discount,total=money(Decimal(str(subtotal))-Decimal(str(discount))),line_ids=lines))
        for i in items:
            qty=quantities[i.id]; i.quantity-=qty; self.move(i,'out',qty,v)
        return self.result({'id':v.id,'name':v.name})
    @http.route('/gems/api/history', type='http', auth='user', methods=['GET'])
    def history(self,kind='transactions',page='0',**kw):
        self.guard(); all_transactions=request.env.user.gems_effective_permissions()['transactions_all']
        if kind in ('in','out'):
            self.require('stock_in_read' if kind=='in' else 'stock_out_read')
            rows=request.env['gems.movement'].sudo().search([('kind','=',kind),('hidden','=',False)],limit=60,offset=max(0,int(page))*60)
            data=[dict(id=r.id,date=str(r.create_date),code=r.code,name=r.name,quantity=r.quantity,reason=r.reason or '',customer=r.customer or '',voucher=r.voucher_id.name or '',staff=r.staff_id.name) for r in rows]
        elif kind=='transactions':
            self.require('transactions_read')
            rows=request.env['gems.voucher'].sudo().search([('cancelled','=',False)] + ([] if all_transactions else [('staff_id','=',request.env.uid)]),limit=60,offset=max(0,int(page))*60)
            data=[dict(id=r.id,date=str(r.create_date),voucher=r.name,customer=r.customer,payment_method=r.payment_method,total=r.total,staff=r.staff_id.name) for r in rows]
        else:raise ValidationError('Unknown history type.')
        return self.result({'rows':data})
    @http.route('/gems/api/voucher/<int:vid>', type='http', auth='user', methods=['GET'])
    def voucher(self,vid,**kw):
        self.guard()
        permissions=request.env.user.gems_effective_permissions()
        if not (permissions['transactions_read'] or permissions['sell']):raise AccessError('Voucher access denied.')
        v=request.env['gems.voucher'].sudo().browse(vid).exists()
        if not v or v.cancelled or (not permissions['transactions_all'] and v.staff_id.id!=request.env.uid): raise AccessError('Voucher unavailable.')
        return self.result(dict(name=v.name,payment_method=v.payment_method,date=str(v.create_date),customer=v.customer,phone=v.phone or '',address=v.address or '',staff=v.staff_id.name,subtotal=v.subtotal,discount=v.discount,percent=v.discount_percent,total=v.total,lines=[dict(code=l.code,name=l.name,qty=l.quantity,price=l.price,amount=l.amount) for l in v.line_ids]))

    @http.route('/gems/api/delete', type='http', auth='user', methods=['POST'])
    def delete(self, kind, record_id, **kw):
        self.delete_permission(kind)
        rid=int(record_id)
        audit={'removed_by':request.env.uid, 'removed_at':fields.Datetime.now()}
        if kind=='item':
            request.env.cr.execute('SELECT id FROM gems_item WHERE id=%s FOR UPDATE',[rid])
            i=request.env['gems.item'].sudo().with_context(active_test=False).browse(rid).exists()
            if not i: raise ValidationError('Item missing.')
            i.invalidate_recordset(['quantity'])
            if i.quantity>0: raise ValidationError('Cannot delete a product with stock. Reduce stock to zero first.')
            i.write(dict(audit,active=False))
        elif kind in ('in','out'):
            r=request.env['gems.movement'].sudo().browse(rid).exists()
            if not r or r.kind!=kind: raise ValidationError('Stock entry missing.')
            r.write(dict(audit,hidden=True))
        elif kind=='transactions':
            request.env.cr.execute('SELECT id FROM gems_voucher WHERE id=%s FOR UPDATE',[rid])
            v=request.env['gems.voucher'].sudo().browse(rid).exists()
            if not v: raise ValidationError('Voucher missing.')
            if not request.env.user.gems_effective_permissions()['transactions_all'] and v.staff_id.id!=request.env.uid:
                raise AccessError('Cannot cancel another staff member’s voucher.')
            v.invalidate_recordset(['cancelled'])
            if not v.cancelled:
                ids=sorted(set(v.line_ids.item_id.ids))
                request.env.cr.execute('SELECT id FROM gems_item WHERE id = ANY(%s) ORDER BY id FOR UPDATE',[ids])
                for line in v.line_ids:
                    i=line.item_id
                    i.invalidate_recordset(['quantity'])
                    i.quantity+=line.quantity
                    self.move(i,'in',line.quantity,v)
                request.env['gems.movement'].sudo().search([('voucher_id','=',v.id),('kind','=','out')]).write(dict(audit,hidden=True))
                v.write(dict(audit,cancelled=True))
        else:
            raise ValidationError('Unknown delete action.')
        return self.result({'ok':True})

    @http.route('/gems/api/staff', type='http', auth='user', methods=['GET'])
    def staff_list(self, page='0', **kw):
        self.guard(True)
        staff=request.env.ref('gems_pos.group_staff')
        manager=request.env.ref('gems_pos.group_manager')
        rows=request.env['res.users'].sudo().search([('group_ids','in',[staff.id]),('group_ids','not in',[manager.id]),('share','=',True)],limit=60,offset=max(0,int(page))*60,order='id desc')
        return self.result({'rows':[{'id':u.id,'name':u.name,'login':u.login,'created':str(u.create_date),'profile':u.gems_profile or 'staff','permissions':u.gems_effective_permissions()} for u in rows]})

    @http.route('/gems/api/staff/create', type='http', auth='user', methods=['POST'])
    def staff_create(self, **kw):
        self.guard(True)
        name=kw.get('name','').strip()
        login=kw.get('login','').strip().lower()
        password=kw.get('password','')
        if not name or len(name)>100:
            raise ValidationError('Staff name is required (maximum 100 characters).')
        if not re.fullmatch(r'[a-z0-9][a-z0-9._@-]{2,79}',login):
            raise ValidationError('Username must be 3–80 characters: letters, numbers, dot, underscore, @ or hyphen.')
        if len(password)<8 or len(password)>128 or not password.strip():
            raise ValidationError('Password must be 8–128 characters.')
        request.env.cr.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',['gems_staff:'+login])
        users=request.env['res.users'].sudo().with_context(active_test=False,no_reset_password=True,mail_create_nolog=True,tracking_disable=True)
        if users.search([('login','=ilike',login)],limit=1):
            return self.result({'ok':False,'message':'Username already exists. Choose another username.'})
        profile=kw.get('profile','staff')
        if profile not in permission_presets():raise ValidationError('Invalid account profile.')
        staff=request.env.ref('gems_pos.group_staff')
        portal=request.env.ref('base.group_portal')
        company=request.env.company
        u=users.create({'name':name,'login':login,'password':password,'company_id':company.id,'company_ids':[(6,0,[company.id])],'group_ids':[(6,0,[portal.id,staff.id])],'gems_profile':profile,'gems_permissions':json.dumps(permission_presets()[profile])})
        return self.result({'ok':True,'name':u.name,'login':u.login})

    @http.route('/gems/api/staff/delete', type='http', auth='user', methods=['POST'])
    def staff_delete(self, record_id, **kw):
        self.guard(True)
        rid=int(record_id)
        request.env.cr.execute('SELECT id FROM res_users WHERE id=%s FOR UPDATE',[rid])
        u=request.env['res.users'].sudo().with_context(active_test=False).browse(rid).exists()
        if not u:
            raise ValidationError('Staff account missing.')
        u.invalidate_recordset()
        if (u.id==request.env.uid or not u.share or
                not u.has_group('gems_pos.group_staff') or
                u.has_group('gems_pos.group_manager') or
                u.has_group('base.group_system')):
            raise AccessError('Only Gems staff accounts can be deleted here.')
        if u.active:
            u.write({'active':False})
        return self.result({'ok':True})

    @http.route('/gems/api/maintenance-ticket', type='http', auth='user', methods=['POST'])
    def maintenance_ticket(self, **kw):
        self.guard(True)
        import base64, hashlib, hmac, time
        from pathlib import Path
        key=Path('/run/gems-maintenance/key').read_bytes()
        payload=base64.urlsafe_b64encode(json.dumps({'uid':request.env.uid,'scope':'gems-maintenance','exp':int(time.time())+1800}).encode()).decode().rstrip('=')
        ticket=payload+'.'+hmac.new(key,payload.encode(),hashlib.sha256).hexdigest()
        response=self.result({'ticket':ticket})
        response.headers['Cache-Control']='no-store'
        return response

    @http.route('/gems/api/stock-reduce', type='http', auth='user', methods=['POST'])
    def stock_reduce(self, item_id, quantity, reason, token, **kw):
        self.require('stock_adjust')
        if not re.fullmatch(r'[0-9]{1,9}',str(quantity)) or int(quantity)<1:
            raise ValidationError('Enter a positive whole quantity to remove.')
        qty=int(quantity);rid=int(item_id);reason=reason.strip()
        if not reason or len(reason)>250:
            raise ValidationError('Reason is required (maximum 250 characters).')
        if not re.fullmatch(r'[a-f0-9]{32}',token):
            raise ValidationError('Invalid correction token.')
        request.env.cr.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',['gems-adjust:'+token])
        movements=request.env['gems.movement'].sudo()
        existing=movements.search([('adjustment_token','=',token)],limit=1)
        if existing:
            if existing.staff_id.id!=request.env.uid or existing.item_id.id!=rid:
                raise AccessError('Invalid correction token owner.')
            return self.result({'ok':True,'duplicate':True})
        request.env.cr.execute('SELECT id FROM gems_item WHERE id=%s FOR UPDATE',[rid])
        i=request.env['gems.item'].sudo().browse(rid).exists()
        if not i: raise ValidationError('Product missing.')
        i.invalidate_recordset(['quantity','active'])
        if not i.active or qty>i.quantity:
            raise ValidationError('Cannot remove more than the current available stock.')
        i.quantity-=qty
        movements.create({'item_id':i.id,'code':i.code,'name':i.name,'kind':'out','quantity':qty,'reason':'Stock correction: '+reason,'adjustment_token':token,'staff_id':request.env.uid})
        return self.result({'ok':True,'remaining':i.quantity})

    @http.route('/gems/api/item/edit', type='http', auth='user', methods=['POST'])
    def edit_item(self, item_id, **kw):
        self.require('products_write')
        rid=int(item_id)
        name=kw.get('name','').strip();code=kw.get('code','').strip();barcode=code;team=kw.get('team','').strip()
        if not re.fullmatch(r'[!-~]{1,32}',code):raise ValidationError('Item code: 1–32 English letters, numbers or symbols, without spaces.')
        try: price=float(kw.get('price',''))
        except (ValueError,TypeError):raise ValidationError('Enter a valid price.')
        if not name or not code or not barcode or max(len(name),len(code),len(barcode),len(team))>200:
            raise ValidationError('Item name, code and barcode are required (maximum 200 characters each).')
        if not math.isfinite(price) or price<0:
            raise ValidationError('Price must be a non-negative finite number.')
        for field in ('quantity','expected_quantity'):
            if not re.fullmatch(r'[0-9]{1,9}',str(kw.get(field,''))):
                raise ValidationError('Stock must be a non-negative whole number.')
        target=int(kw['quantity']);expected=int(kw['expected_quantity'])
        token=kw.get('token','')
        if not re.fullmatch(r'[a-f0-9]{32}',token):
            raise ValidationError('Invalid edit token. Refresh and try again.')
        request.env.cr.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',['gems-adjust:'+token])
        movements=request.env['gems.movement'].sudo()
        existing=movements.search([('adjustment_token','=',token)],limit=1)
        if existing:
            if existing.staff_id.id!=request.env.uid or existing.item_id.id!=rid:
                raise AccessError('Invalid edit token owner.')
            return self.result({'ok':True,'duplicate':True})
        request.env.cr.execute('SELECT id FROM gems_item WHERE id=%s FOR UPDATE',[rid])
        i=request.env['gems.item'].sudo().browse(rid).exists()
        if not i: raise ValidationError('Product missing.')
        i.invalidate_recordset()
        if not i.active:raise ValidationError('This product has been deleted. Refresh the catalog.')
        vals={'name':name,'code':code,'barcode':barcode,'team':team,'price':money(price)}
        vals.update(self.cost_values(kw))
        delta=0
        if target!=expected:
            self.require('stock_adjust')
            if i.quantity!=expected:
                raise ValidationError('Stock changed while editing. Reopen the product and try again.')
            delta=target-i.quantity
            vals['quantity']=target
        upload=request.httprequest.files.get('image')
        if upload:
            data=upload.read(3*1024*1024+1)
            if len(data)>3*1024*1024:raise ValidationError('Photo maximum is 3 MB.')
            if data:
                try:
                    image=Image.open(BytesIO(data))
                    if image.format not in ('PNG','JPEG','WEBP'):raise ValueError()
                    image.verify()
                except Exception:raise ValidationError('Use a valid PNG, JPEG or WebP photo.')
                vals['image']=base64.b64encode(data)
        if 'image' not in vals and kw.get('remove_image')=='1':vals['image']=False
        i.write(vals)
        if delta:
            movements.create({'item_id':i.id,'code':i.code,'name':i.name,
                'kind':'in' if delta>0 else 'out','quantity':abs(delta),
                'reason':'Product edit: stock %s → %s' % (expected,target),
                'adjustment_token':token,'staff_id':request.env.uid})
        return self.result({'ok':True,'remaining':i.quantity})

    @http.route('/gems/api/delete-selected', type='http', auth='user', methods=['POST'])
    def delete_selected(self, kind, record_ids, **kw):
        self.delete_permission(kind)
        if kind not in ('in','out','transactions'):raise ValidationError('Invalid history type.')
        try: ids=json.loads(record_ids)
        except (ValueError,TypeError):raise ValidationError('Invalid selection.')
        if not isinstance(ids,list) or not ids or len(ids)>60 or any(type(i) is not int or i<1 for i in ids):
            raise ValidationError('Select 1–60 valid records.')
        ids=sorted(set(ids))
        if kind=='transactions':
            request.env.cr.execute('SELECT id FROM gems_voucher WHERE id = ANY(%s) ORDER BY id FOR UPDATE',[ids])
            vouchers=request.env['gems.voucher'].sudo().browse(ids).exists()
            if len(vouchers)!=len(ids):raise ValidationError('A voucher is missing. Refresh the list.')
            if not request.env.user.gems_effective_permissions()['transactions_all'] and any(v.staff_id.id!=request.env.uid for v in vouchers):
                raise AccessError('Cannot cancel another staff member’s voucher.')
            item_ids=sorted(set(vouchers.line_ids.item_id.ids))
            request.env.cr.execute('SELECT id FROM gems_item WHERE id = ANY(%s) ORDER BY id FOR UPDATE',[item_ids])
        else:
            request.env.cr.execute('SELECT id FROM gems_movement WHERE id = ANY(%s) ORDER BY id FOR UPDATE',[ids])
            rows=request.env['gems.movement'].sudo().browse(ids).exists()
            if len(rows)!=len(ids) or any(row.kind!=kind for row in rows):
                raise ValidationError('A stock record is missing or has the wrong type.')
        for rid in ids:self.delete(kind,str(rid))
        return self.result({'ok':True,'count':len(ids)})

    @http.route('/gems/api/scan', type='http', auth='user', methods=['GET'])
    def scan(self, code='', **kw):
        self.require('products_read')
        if not code or len(code)>200:raise ValidationError('Invalid scan.')
        i=request.env['gems.item'].sudo().search([('code','=',code)],limit=1)
        if not i:return self.result({'item':None})
        return self.result({'item':{'id':i.id,'name':i.name,'code':i.code,'barcode':i.code,
            'price':i.price,'quantity':i.quantity,'team':i.team or ''}})

    @http.route('/gems/api/stockin-labels', type='http', auth='user', methods=['POST'])
    def stockin_labels(self, record_ids, **kw):
        self.require('stock_in_read');self.require('barcode_print')
        try:ids=json.loads(record_ids)
        except (ValueError,TypeError):raise ValidationError('Invalid selection.')
        if not isinstance(ids,list) or not ids or len(ids)>60 or any(type(i) is not int or i<1 for i in ids):
            raise ValidationError('Select 1–60 Stock In rows.')
        ids=sorted(set(ids))
        rows=request.env['gems.movement'].sudo().browse(ids).exists()
        if len(rows)!=len(ids) or any(row.kind!='in' or row.hidden for row in rows):
            raise ValidationError('A Stock In row is unavailable. Refresh and select again.')
        products={}
        for row in rows:
            i=row.item_id
            if not i.active:raise ValidationError('A selected product has been deleted. Select active products.')
            if i.id not in products:products[i.id]={'id':i.id,'name':i.name,'code':i.code,'received':0}
            products[i.id]['received']+=row.quantity
        return self.result({'items':list(products.values())})

    @http.route('/gems/api/staff/permissions', type='http', auth='user', methods=['POST'])
    def staff_permissions(self, record_id, permissions, profile='custom', **kw):
        self.guard(True)
        try:data=normalize_permissions(json.loads(permissions))
        except (ValueError,TypeError):raise ValidationError('Invalid permissions JSON.')
        if profile not in ('staff','manager','readonly','custom'):raise ValidationError('Invalid profile.')
        rid=int(record_id)
        request.env.cr.execute('SELECT id FROM res_users WHERE id=%s FOR UPDATE',[rid])
        u=request.env['res.users'].sudo().browse(rid).exists()
        if not u or not u.active or u.id==request.env.uid or not u.share or not u.has_group('gems_pos.group_staff') or u.has_group('gems_pos.group_manager') or u.has_group('base.group_system'):
            raise AccessError('Only active Gems website accounts can be configured here. Administrator accounts are protected.')
        u.write({'gems_permissions':json.dumps(data),'gems_profile':profile,
            'gems_permissions_updated_by':request.env.uid,'gems_permissions_updated_at':fields.Datetime.now()})
        return self.result({'ok':True,'permissions':data})

    @http.route('/gems/api/product-label/<int:item_id>', type='http', auth='user', methods=['GET'])
    def product_label(self, item_id, **kw):
        self.require('products_read');self.require('barcode_print')
        i=request.env['gems.item'].sudo().browse(item_id).exists()
        if not i or not i.active:raise ValidationError('Product unavailable.')
        return self.result({'id':i.id,'name':i.name,'code':i.code,'received':1})

    def cost_values(self, kw):
        if 'cost_price' not in kw:return {}
        self.guard(True)
        raw=str(kw['cost_price']).strip()
        if not raw:return {'cost_price':0,'cost_known':False}
        try:cost=float(raw)
        except (TypeError,ValueError):raise ValidationError('Enter a valid cost price.')
        if not math.isfinite(cost) or cost<0 or cost>999999999999:
            raise ValidationError('Cost must be a finite non-negative number.')
        return {'cost_price':money(cost),'cost_known':True}

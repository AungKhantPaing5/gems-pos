from odoo import models, fields, api
from odoo.exceptions import ValidationError

class Item(models.Model):
    _name = 'gems.item'
    _description = 'Gem Item'
    _order = 'id desc'
    name = fields.Char(required=True, index=True)
    code = fields.Char(required=True, index=True)
    barcode = fields.Char(required=True, index=True)
    team = fields.Char(index=True)
    price = fields.Float(required=True, digits=(16, 2))
    cost_price = fields.Float(digits=(16, 2), groups="gems_pos.group_manager")
    cost_known = fields.Boolean(default=False, groups="gems_pos.group_manager")
    quantity = fields.Integer(default=0, readonly=True)
    image = fields.Image(max_width=640, max_height=640)
    active = fields.Boolean(default=True)
    removed_by = fields.Many2one('res.users')
    removed_at = fields.Datetime()
    _code_unique = models.Constraint('UNIQUE(code)', 'Item code already exists.')
    _barcode_unique = models.Constraint('UNIQUE(barcode)', 'Barcode already exists.')
    _cost_nonnegative = models.Constraint('CHECK(cost_price >= 0)', 'Cost cannot be negative.')
    _positive = models.Constraint('CHECK(price >= 0 AND quantity >= 0)', 'Price/stock cannot be negative.')

    @api.model_create_multi
    def create(self, vals_list):
        vals_list=[dict(v,barcode=v.get('code')) for v in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        vals=dict(vals)
        if 'code' in vals: vals['barcode']=vals['code']
        elif 'barcode' in vals: raise ValidationError('Edit the item code to change the barcode.')
        if vals.get('active') is False:
            self.env.cr.execute('SELECT id FROM gems_item WHERE id = ANY(%s) ORDER BY id FOR UPDATE', [sorted(self.ids)])
            self.invalidate_recordset(['quantity'])
            if any(i.quantity > 0 for i in self):
                raise ValidationError('Cannot delete a product with stock. Reduce stock to zero first.')
        return super().write(vals)

class Movement(models.Model):
    _name = 'gems.movement'
    _description = 'Stock Ledger'
    create_date = fields.Datetime(index=True, readonly=True)
    _order = 'id desc'
    item_id = fields.Many2one('gems.item', required=True, ondelete='restrict', index=True)
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    hidden = fields.Boolean(default=False, index=True)
    removed_by = fields.Many2one('res.users')
    removed_at = fields.Datetime()
    kind = fields.Selection([('in', 'Stock In'), ('out', 'Stock Out')], required=True, index=True)
    quantity = fields.Integer(required=True)
    reason = fields.Char()
    adjustment_token = fields.Char(index=True)
    _adjustment_unique = models.Constraint('UNIQUE(adjustment_token)', 'Stock correction already applied.')
    customer = fields.Char()
    voucher_id = fields.Many2one('gems.voucher', ondelete='restrict', index=True)
    staff_id = fields.Many2one('res.users', required=True)
    _positive = models.Constraint('CHECK(quantity > 0)', 'Quantity must be positive.')

class Voucher(models.Model):
    _name = 'gems.voucher'
    _description = 'Sales Voucher'
    create_date = fields.Datetime(index=True, readonly=True)
    _order = 'id desc'
    name = fields.Char(required=True, index=True)
    payment_method = fields.Char(required=True, default='Not recorded')
    cancelled = fields.Boolean(default=False, index=True)
    removed_by = fields.Many2one('res.users')
    removed_at = fields.Datetime()
    token = fields.Char(required=True, index=True)
    customer = fields.Char(required=True)
    phone = fields.Char()
    address = fields.Text()
    staff_id = fields.Many2one('res.users', required=True)
    discount_percent = fields.Float(digits=(16, 2))
    subtotal = fields.Float(digits=(16, 2))
    discount = fields.Float(digits=(16, 2))
    total = fields.Float(digits=(16, 2))
    line_ids = fields.One2many('gems.line', 'voucher_id')
    _token_unique = models.Constraint('UNIQUE(token)', 'Voucher already submitted.')
    _discount_valid = models.Constraint('CHECK(discount_percent >= 0 AND discount_percent <= 100)', 'Invalid discount.')

class Line(models.Model):
    _name = 'gems.line'
    _description = 'Voucher Line'
    voucher_id = fields.Many2one('gems.voucher', required=True, ondelete='cascade', index=True)
    item_id = fields.Many2one('gems.item', required=True, ondelete='restrict')
    code = fields.Char()
    name = fields.Char()
    quantity = fields.Integer(required=True)
    price = fields.Float(digits=(16, 2))
    amount = fields.Float(digits=(16, 2))
    cost_price = fields.Float(digits=(16, 2), groups='gems_pos.group_manager')
    cost_known = fields.Boolean(default=False, groups='gems_pos.group_manager')


class Expense(models.Model):
    _name = 'gems.expense'
    _description = 'Shop operating expense'
    _order = 'date desc, id desc'
    date = fields.Date(required=True, index=True)
    name = fields.Char(required=True)
    amount = fields.Float(required=True, digits=(16, 2))
    token = fields.Char(required=True, index=True)
    staff_id = fields.Many2one('res.users', required=True)
    voided = fields.Boolean(default=False)
    voided_by = fields.Many2one('res.users')
    voided_at = fields.Datetime()
    _token_unique = models.Constraint('UNIQUE(token)', 'Expense already saved.')
    _positive = models.Constraint('CHECK(amount > 0)', 'Expense must be positive.')

import json
from odoo import models, fields, api
from odoo.exceptions import AccessError, ValidationError

PERMISSION_LABELS = {
    'products_read': 'Products: view',
    'products_write': 'Products: add / edit / photo / price',
    'products_delete': 'Products: delete (zero stock only)',
    'stock_adjust': 'Stock: receive / reduce / edit quantity',
    'stock_in_read': 'Stock In: view',
    'stock_in_delete': 'Stock In: delete history',
    'stock_out_read': 'Stock Out: view',
    'stock_out_delete': 'Stock Out: delete history',
    'transactions_read': 'Transactions: view own vouchers',
    'transactions_all': 'Transactions: view all staff vouchers',
    'transactions_delete': 'Transactions: cancel / delete (returns stock)',
    'barcode_print': 'Barcode: print labels',
    'sell': 'Sales desk: complete sales',
}
DEPENDENCIES = {
    'products_write': 'products_read', 'products_delete': 'products_read',
    'stock_adjust': 'products_read', 'sell': 'products_read',
    'barcode_print': 'products_read', 'stock_in_delete': 'stock_in_read',
    'stock_out_delete': 'stock_out_read', 'transactions_all': 'transactions_read',
    'transactions_delete': 'transactions_read',
}

def normalize_permissions(data):
    if not isinstance(data, dict) or set(data)-set(PERMISSION_LABELS):
        raise ValidationError('Invalid permissions.')
    if any(type(v) is not bool for v in data.values()):
        raise ValidationError('Permissions must be true or false.')
    result={k:data.get(k,False) for k in PERMISSION_LABELS}
    for child,parent in DEPENDENCIES.items():
        if result[child]:result[parent]=True
    return result

def permission_presets():
    staff=normalize_permissions({'products_read':True,'transactions_read':True,'sell':True})
    manager=normalize_permissions(dict(staff,products_write=True,stock_adjust=True,stock_in_read=True,
        stock_out_read=True,transactions_all=True,barcode_print=True))
    readonly=normalize_permissions({'products_read':True,'transactions_read':True})
    return {'staff':staff,'manager':manager,'readonly':readonly}

class GemsUser(models.Model):
    _inherit='res.users'
    gems_permissions = fields.Text(groups='gems_pos.group_manager', copy=False)
    gems_profile = fields.Selection([('staff','Staff'),('manager','Manager'),('readonly','Read only'),('custom','Custom')],
        default='staff', groups='gems_pos.group_manager', copy=False)
    gems_permissions_updated_by = fields.Many2one('res.users', groups='gems_pos.group_manager', copy=False)
    gems_permissions_updated_at = fields.Datetime(groups='gems_pos.group_manager', copy=False)

    def gems_effective_permissions(self):
        self.ensure_one()
        if self.has_group('gems_pos.group_manager'):
            return {k:True for k in PERMISSION_LABELS}
        raw=self.sudo().gems_permissions
        if not raw:return permission_presets()['staff']
        try:return normalize_permissions(json.loads(raw))
        except (ValueError,TypeError,ValidationError):return {k:False for k in PERMISSION_LABELS}

    def _check_gems_permission_write(self, vals):
        protected={'gems_permissions','gems_profile','gems_permissions_updated_by','gems_permissions_updated_at'}
        if protected.intersection(vals) and not (self.env.su or self.env.user.has_group('gems_pos.group_manager')):
            raise AccessError('Only an administrator can change Gems permissions.')
        if vals.get('gems_permissions'):
            vals['gems_permissions']=json.dumps(normalize_permissions(json.loads(vals['gems_permissions'])))

    @api.model_create_multi
    def create(self, vals_list):
        vals_list=[dict(v) for v in vals_list]
        for vals in vals_list:self._check_gems_permission_write(vals)
        return super().create(vals_list)

    def write(self, vals):
        vals=dict(vals);self._check_gems_permission_write(vals)
        return super().write(vals)

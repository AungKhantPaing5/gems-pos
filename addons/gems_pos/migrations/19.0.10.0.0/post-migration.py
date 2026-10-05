import uuid

def migrate(cr, version):
    # Keep historical voucher/ledger snapshots; only live and archived product barcodes change.
    cr.execute('LOCK TABLE gems_item IN EXCLUSIVE MODE')
    prefix='gems-merge-'+uuid.uuid4().hex+'-'
    cr.execute('UPDATE gems_item SET barcode=%s || id::text', [prefix])
    cr.execute('UPDATE gems_item SET barcode=code')

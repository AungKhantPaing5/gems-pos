manager=env.ref('gems_pos.group_manager')
staff=env.ref('gems_pos.group_staff')
admin=env.ref('base.user_admin')
admin.write({'login':'admin','password':'admin','group_ids':[(4,manager.id)]})
u=env['res.users'].search([('login','=','user')],limit=1)
if not u:
    u=env['res.users'].with_context(no_reset_password=True).create({'name':'Sales Staff','login':'user','password':'user','group_ids':[(6,0,[env.ref('base.group_portal').id,staff.id])]})
else:
    raise Exception('Login user already exists; inspect it before assigning staff permissions.')
env.cr.commit()
print('Gems accounts configured.')

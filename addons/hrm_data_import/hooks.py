"""Create draft configuration templates, never business transactions."""


def post_init_hook(env):
    create_company_templates(env, env['hrm.company'].search([]))


def create_company_templates(env, companies):
    for company in companies:
        identity = ['employee_code', 'source_record_id', 'revision', 'approval_reference']
        for suffix, label, dataset, extra in [
            ('daily', 'Công theo ngày', 'attendance', ['work_date', 'regular_hours']),
            ('monthly', 'Công tháng ngang', 'attendance', [f'D{d:02}' for d in range(1, 32)]),
            ('performance', 'Hiệu quả nhiều cột', 'performance', ['HIEU_QUA_1', 'HIEU_QUA_2']),
            ('salary', 'Đầu vào lương', 'salary', ['component_code', 'amount', 'currency']),
            ('history', 'Lương lịch sử', 'history', ['component_code', 'amount', 'currency']),
        ]:
            source = 'MANUAL-' + suffix.upper()
            if env['hrm.import.profile'].search_count([('company_id', '=', company.id), ('source', '=', source)]):
                continue
            targets = identity + ([] if suffix in ('monthly', 'performance') else extra)
            mappings = [(0, 0, dict(column=i, target=target,
                data_type='number' if target in ('revision', 'regular_hours', 'amount') else ('date' if target == 'work_date' else 'text'),
                required=True)) for i, target in enumerate(targets, 1)]
            if suffix == 'performance':
                mappings += [(0, 0, dict(column=i, target='amount', data_type='number', required=False)) for i in (5, 6)]
            env['hrm.import.profile'].create(dict(
                name=f'Mẫu {label} - {company.name}', company_id=company.id, tenant_id=company.tenant_id.id,
                dataset=dataset, source=source, headers=identity + extra, locale='vi',
                monthly=suffix == 'monthly', first_day_column=5, symbols={'X': 8, 'KL': 0},
                amount_columns=suffix == 'performance', mapping_ids=mappings))

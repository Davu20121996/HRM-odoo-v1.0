"""Read-only timesheets over payroll's imported attendance; never copy hours."""
from odoo import fields, models


def available_years(records):
    years = {str(p.period_start.year) for p in records.env['hrm.payroll.period'].search([])}
    return [(year, year) for year in sorted(years, reverse=True)]


MONTHS = [(str(n), f'Month {n:02}') for n in range(1, 13)]


class AttendanceMonth(models.Model):
    _name = 'hrm.attendance.month'
    _description = 'All employee monthly attendance'
    _auto = False
    _rec_name = 'employee_id'
    _order = 'period_start desc, employee_code'

    company_id = fields.Many2one('hrm.company', string='Company', readonly=True)
    tenant_id = fields.Many2one('hrm.tenant', readonly=True)
    period_id = fields.Many2one('hrm.payroll.period', string='Attendance period', readonly=True)
    period_start = fields.Date(string='From date', readonly=True)
    period_label = fields.Char(string='Period', readonly=True)
    year = fields.Selection(available_years, string='Year', readonly=True)
    month = fields.Selection(MONTHS, string='Month', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employees', readonly=True)
    employee_code = fields.Char(string='Employee code', readonly=True)
    assignment_department = fields.Char(string='Phòng ban', compute='_compute_assignment_labels')
    assignment_projects = fields.Char(string='Dự án', compute='_compute_assignment_labels')
    employment_status = fields.Char(string='Employment status', readonly=True)
    standard_days = fields.Float(string='Standard days', readonly=True)
    total_hours = fields.Float(string='Total hours', digits=(12, 2), readonly=True)
    overtime_hours = fields.Float(string='Giờ tăng ca', digits=(12, 2), readonly=True)
    total_days = fields.Float(string='Paid days', digits=(12, 2), readonly=True)
    recorded_days = fields.Integer(string='Days with data', readonly=True)
    source_count = fields.Integer(string='Source rows', readonly=True)
    data_state = fields.Char(string='Attendance data', readonly=True)
    for _day in range(1, 32):
        locals()[f'd{_day:02}'] = fields.Char(string=f'{_day:02}', readonly=True,
            help=f'Hours on day {_day:02}. Blank: no source; 0: recorded zero hours; —: day does not exist in this month.')
    del _day

    def _compute_assignment_labels(self):
        for period, rows in self.grouped('period_id').items():
            assignments = rows.employee_id._primary_assignments(period.period_end)
            for row in rows:
                assignment = assignments.get(row.employee_id.id, self.env['hrm.employee.assignment'])
                row.assignment_department = assignment.department_id.name
                row.assignment_projects = ', '.join(assignment.project_ids.mapped('name'))

    def init(self):
        columns = []
        for day in range(1, 32):
            value = f"SUM(d.hours) FILTER (WHERE EXTRACT(DAY FROM d.work_date)={day})"
            columns.append(f"""CASE
                WHEN {day}>EXTRACT(DAY FROM (date_trunc('month',p.period_start)+interval '1 month - 1 day')) THEN '—'
                WHEN {value} IS NULL THEN ''
                ELSE trim(trailing '.' from to_char({value},'FM999990.9999'))
                END AS d{day:02}""")
        self.env.cr.execute(f"""
            CREATE OR REPLACE VIEW hrm_attendance_month AS
            WITH daily AS (
                SELECT company_id,period_id,employee_id,
                    (payload->>'work_date')::date AS work_date,
                    SUM((payload->>'regular_hours')::numeric) AS hours,
                    SUM(COALESCE((payload->>'overtime_hours')::numeric,0)) AS overtime,
                    COUNT(*) AS sources
                FROM hrm_import_input WHERE dataset='attendance'
                GROUP BY company_id,period_id,employee_id,(payload->>'work_date')::date
            )
            SELECT (p.id::bigint*4294967296+e.id::bigint) AS id,
                p.tenant_id,p.company_id,p.id AS period_id,p.period_start,
                EXTRACT(YEAR FROM p.period_start)::integer::text AS year,
                EXTRACT(MONTH FROM p.period_start)::integer::text AS month,
                e.id AS employee_id,e.employee_code,e.current_status AS employment_status,
                p.standard_days,COALESCE(SUM(d.hours),0)::double precision AS total_hours,
                (COALESCE(SUM(d.hours),0)/NULLIF(p.hours_per_day,0))::double precision AS total_days,
                COUNT(d.work_date)::integer AS recorded_days,
                COALESCE(SUM(d.sources),0)::integer AS source_count,
                CASE WHEN COUNT(d.work_date)=0 THEN 'Chưa có công' ELSE 'Đã có công' END AS data_state,
                {','.join(columns)},to_char(p.period_start,'MM/YYYY') AS period_label,
                COALESCE(SUM(d.overtime),0)::double precision AS overtime_hours
            FROM hrm_payroll_period p
            JOIN hr_employee e ON e.hrm_company_id=p.company_id AND e.tenant_id=p.tenant_id
            LEFT JOIN daily d ON d.company_id=p.company_id AND d.period_id=p.id AND d.employee_id=e.id
                AND d.work_date BETWEEN p.period_start AND p.period_end
            GROUP BY p.id,e.id
        """)

    def action_details(self):
        self.ensure_one()
        self.check_access('read')
        return {'type': 'ir.actions.act_window', 'name': 'Chi tiết công từng ngày',
            'res_model': 'hrm.attendance.day', 'view_mode': 'list,pivot',
            'domain': [('company_id', '=', self.company_id.id), ('period_id', '=', self.period_id.id),
                       ('employee_id', '=', self.employee_id.id)]}

    def action_monthly_workspace(self):
        self.ensure_one()
        self.check_access('read')
        screen = self.env['hrm.monthly.workspace'].search([('company_id', '=', self.company_id.id),
            ('employee_id', '=', self.employee_id.id), ('year', '=', int(self.year)), ('month', '=', self.month)], limit=1)
        if not screen:
            screen = self.env['hrm.monthly.workspace'].create(dict(company_id=self.company_id.id,
                employee_id=self.employee_id.id, year=int(self.year), month=self.month))
        screen.action_refresh()
        return {'type': 'ir.actions.act_window', 'res_model': 'hrm.monthly.workspace',
                'view_mode': 'form', 'res_id': screen.id}


class AttendanceDay(models.Model):
    _name = 'hrm.attendance.day'
    _description = 'Recorded daily attendance details'
    _auto = False
    _rec_name = 'employee_id'
    _order = 'work_date desc, employee_code, id'
    company_id = fields.Many2one('hrm.company', string='Company', readonly=True)
    period_id = fields.Many2one('hrm.payroll.period', string='Attendance period', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employees', readonly=True)
    employee_code = fields.Char(string='Employee code', readonly=True)
    year = fields.Selection(available_years, string='Year', readonly=True)
    month = fields.Selection(MONTHS, string='Month', readonly=True)
    work_date = fields.Date(string='Paid days', readonly=True)
    hours = fields.Float(string='Recorded hours', digits=(12, 4), readonly=True)
    overtime_hours = fields.Float(string='Giờ tăng ca', digits=(12, 4), readonly=True)
    attendance_symbol = fields.Char(string='Ký hiệu', readonly=True)
    project_code = fields.Char(string='Project', readonly=True)
    source = fields.Char(string='Source', readonly=True)
    revision = fields.Integer(string='Version', readonly=True)
    approval_reference = fields.Char(string='Approval / reason', readonly=True)
    batch_id = fields.Many2one('hrm.import.batch', string='Import batch / log', readonly=True)

    def init(self):
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW hrm_attendance_day AS
            SELECT i.id,i.company_id,i.period_id,i.employee_id,e.employee_code,
                EXTRACT(YEAR FROM p.period_start)::integer::text AS year,
                EXTRACT(MONTH FROM p.period_start)::integer::text AS month,
                (i.payload->>'work_date')::date AS work_date,
                (i.payload->>'regular_hours')::double precision AS hours,
                i.payload->>'project_code' AS project_code,i.source,i.revision,
                i.payload->>'approval_reference' AS approval_reference,i.batch_id,
                COALESCE((i.payload->>'overtime_hours')::double precision,0) AS overtime_hours,
                i.payload->>'attendance_symbol' AS attendance_symbol
            FROM hrm_import_input i
            JOIN hr_employee e ON e.id=i.employee_id
            JOIN hrm_payroll_period p ON p.id=i.period_id
            WHERE i.dataset='attendance'
        """)

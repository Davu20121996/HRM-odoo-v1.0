from odoo import fields, models


class HrmCompany(models.Model):
    _name = "hrm.company"
    _inherit = ["hrm.base.mixin"]
    _description = "Operating company inside a tenant (SPEC §3.2)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    parent_company_id = fields.Many2one("hrm.company", ondelete="restrict")
    child_ids = fields.One2many("hrm.company", "parent_company_id")
    res_company_id = fields.Many2one(
        "res.company",
        help="Adapter link to the Odoo company (master-skill §7).",
        ondelete="set null",
    )
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    legal_name = fields.Char()
    registration_no = fields.Char()
    country_code = fields.Char(size=2)
    currency_code = fields.Char(required=True, default="USD", size=3)
    timezone = fields.Char()
    status = fields.Selection(
        [("active", "Active"), ("suspended", "Suspended"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _tenant_code_unique = models.Constraint(
        "UNIQUE(tenant_id, code)", "Company code must be unique per tenant."
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Company UUID must be unique.")


class HrmBusinessUnit(models.Model):
    _name = "hrm.business.unit"
    _inherit = ["hrm.base.mixin"]
    _description = "Business unit (SPEC §3.3)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    parent_id = fields.Many2one("hrm.business.unit", ondelete="restrict")
    child_ids = fields.One2many("hrm.business.unit", "parent_id")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    manager_user_id = fields.Many2one(
        "res.users",
        help="TODO P2: switch to hr.employee link (manager_employee_id).",
        ondelete="set null",
    )
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _tenant_company_code_unique = models.Constraint(
        "UNIQUE(tenant_id, company_id, code)",
        "Business unit code must be unique per tenant+company.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Business unit UUID must be unique.")


class HrmDepartment(models.Model):
    _name = "hrm.department"
    _inherit = ["hrm.base.mixin"]
    _description = "Department, effective-dated (SPEC §3.4)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    business_unit_id = fields.Many2one("hrm.business.unit", ondelete="restrict")
    parent_id = fields.Many2one("hrm.department", ondelete="restrict")
    child_ids = fields.One2many("hrm.department", "parent_id")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    manager_user_id = fields.Many2one(
        "res.users",
        help="TODO P2: switch to hr.employee link (manager_employee_id).",
        ondelete="set null",
    )
    cost_center_id = fields.Many2one("hrm.cost.center", ondelete="restrict")
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )
    effective_from = fields.Date(required=True, default=fields.Date.today)
    effective_to = fields.Date()

    _tenant_company_code_unique = models.Constraint(
        "UNIQUE(tenant_id, company_id, code)",
        "Department code must be unique per tenant+company.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Department UUID must be unique.")


class HrmLocation(models.Model):
    _name = "hrm.location"
    _inherit = ["hrm.base.mixin"]
    _description = "Work location (SPEC §3.5)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    parent_id = fields.Many2one("hrm.location", ondelete="restrict")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    location_type = fields.Selection(
        [("office", "Office"), ("factory", "Factory"), ("site", "Site"), ("remote", "Remote")],
        default="office",
        required=True,
    )
    address_line1 = fields.Char()
    address_line2 = fields.Char()
    city = fields.Char()
    state = fields.Char()
    postal_code = fields.Char()
    country_code = fields.Char(size=2)
    timezone = fields.Char()
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _tenant_company_code_unique = models.Constraint(
        "UNIQUE(tenant_id, company_id, code)",
        "Location code must be unique per tenant+company.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Location UUID must be unique.")


class HrmCostCenter(models.Model):
    _name = "hrm.cost.center"
    _inherit = ["hrm.base.mixin"]
    _description = "Cost center (SPEC §3.6)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    company_id = fields.Many2one("hrm.company", required=True, ondelete="restrict")
    parent_id = fields.Many2one("hrm.cost.center", ondelete="restrict")
    code = fields.Char(required=True)
    name = fields.Char(required=True)
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )

    _tenant_company_code_unique = models.Constraint(
        "UNIQUE(tenant_id, company_id, code)",
        "Cost center code must be unique per tenant+company.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Cost center UUID must be unique.")

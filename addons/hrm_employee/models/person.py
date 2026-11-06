from odoo import api, fields, models


class HrmPerson(models.Model):
    """Canonical human identity. Not an employee, not a login account.

    Country-specific identifiers (CCCD, BHXH...) live in the VN
    localization package, never here (master-skill §2.2, §6).
    """

    _name = "hrm.person"
    _inherit = ["hrm.base.mixin"]
    _description = "Person (SPEC §4.1)"

    tenant_id = fields.Many2one("hrm.tenant", required=True, ondelete="restrict")
    person_code = fields.Char()
    first_name = fields.Char(required=True)
    middle_name = fields.Char()
    last_name = fields.Char(required=True)
    display_name = fields.Char(compute="_compute_display_name", store=True)
    preferred_name = fields.Char()
    date_of_birth = fields.Date()
    gender = fields.Selection(
        [("male", "Male"), ("female", "Female"), ("other", "Other")],
    )
    nationality_code = fields.Char(size=2)
    marital_status = fields.Selection(
        [
            ("single", "Single"),
            ("married", "Married"),
            ("divorced", "Divorced"),
            ("widowed", "Widowed"),
        ],
    )
    photo = fields.Image()
    status = fields.Selection(
        [("active", "Active"), ("archived", "Archived")],
        default="active",
        required=True,
    )
    employee_ids = fields.One2many("hr.employee", "person_id")

    _tenant_person_code_unique = models.Constraint(
        "UNIQUE(tenant_id, person_code)",
        "Person code must be unique per tenant.",
    )
    _uuid_unique = models.Constraint("UNIQUE(uuid)", "Person UUID must be unique.")

    @api.depends("first_name", "middle_name", "last_name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = " ".join(
                p for p in [rec.first_name, rec.middle_name, rec.last_name] if p
            )

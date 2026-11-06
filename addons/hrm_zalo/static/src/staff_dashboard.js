import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

class StaffDashboard extends Component {
    static template = "hrm_zalo.StaffDashboard";
    props = useProps(standardFieldProps);

    get data() {
        return JSON.parse(this.props.record.data[this.props.name] || "{}");
    }

    get categories() {
        const data = this.data;
        const rows = [
            { label: "Đang làm việc", count: data.working || 0, color: "blue", icon: "fa-users" },
            { label: "Nghỉ thai sản", count: data.maternity || 0, color: "pink", icon: "fa-heart" },
            { label: "Mới vào tháng này", count: data.new || 0, color: "green", icon: "fa-user-plus" },
            { label: "Thực tập sinh", count: data.interns || 0, color: "amber", icon: "fa-graduation-cap" },
        ];
        const max = Math.max(1, ...rows.map((row) => row.count));
        return rows.map((row) => ({ ...row, width: 100 * row.count / max }));
    }
}

registry.category("fields").add("smb_staff_dashboard", { component: StaffDashboard, supportedTypes: ["char"] });

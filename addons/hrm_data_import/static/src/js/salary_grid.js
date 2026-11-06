import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class SalaryGrid extends Component {
    static template = "hrm_data_import.SalaryGrid";

    setup() {
        this.orm = useService("orm");
        const props = useProps({ action: t.object() });
        this.state = proxy({ grid: { periods: [], rows: [], columns: [] }, edits: {}, busy: false,
            operation: "", reason: "", message: "", error: false });
        onWillStart(() => this.load(props.action.context?.salary_grid_period_id || false));
    }

    async load(periodId) {
        this.state.grid = await this.orm.call("hrm.payroll.period", "load_salary_grid", [periodId]);
        this.state.edits = {};
        this.state.operation = "";
        this.state.reason = "";
    }

    async selectPeriod(event) {
        this.state.message = "";
        await this.load(Number(event.target.value));
    }

    get editable() {
        return ["open", "manual"].includes(this.state.grid.mode);
    }

    key(row, column) {
        return row.id + ":" + column.id;
    }

    edit(row, column, value) {
        const cell = row.values[column.id];
        const key = this.key(row, column);
        if (value === "" && !cell.manual) {
            delete this.state.edits[key];
        } else {
            this.state.edits[key] = { employee_id: row.id, component_id: column.id,
                revision: cell.revision, amount: value === "" ? null : Number(value) };
        }
    }

    input(row, column) {
        const change = this.state.edits[this.key(row, column)];
        return change ? change.amount ?? "" : row.values[column.id]?.amount ?? "";
    }

    money(value) {
        return value === null || value === undefined ? "—" : new Intl.NumberFormat("vi-VN").format(value);
    }

    request(operation) {
        this.state.operation = operation;
        this.state.reason = "";
        this.state.message = "";
    }

    async submit(event) {
        event.preventDefault();
        await this.execute(this.state.operation);
    }

    async execute(operation) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        this.state.message = "";
        try {
            const periodId = this.state.grid.period_id;
            await this.orm.call("hrm.payroll.period", "update_salary_grid", [
                periodId, operation, Object.values(this.state.edits), this.state.reason,
            ]);
            await this.load(periodId);
            this.state.error = false;
            this.state.message = {
                calculate: "Đã tính lương theo công thức.", save: "Đã lưu và tính lại lương.",
                lock: "Đã khóa lương và công.", unlock: "Đã mở khóa lương. Có thể sửa công nếu kỳ công không bị khóa riêng.",
            }[operation];
        } catch (error) {
            this.state.error = true;
            this.state.message = error.data?.message || error.message;
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("actions").add("hrm_salary_grid", SalaryGrid);

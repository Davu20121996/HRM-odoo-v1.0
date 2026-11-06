import { Component, onWillStart, proxy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class AttendanceGrid extends Component {
    static template = "hrm_data_import.AttendanceGrid";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ grid: { periods: [], rows: [] }, edits: {}, busy: false, message: "", error: false, batchId: false, employeeQuery: "" });
        this.state.symbolForm = null;
        onWillStart(() => this.load());
    }

    async load(periodId = false) {
        this.state.busy = true;
        try {
            this.state.grid = await this.orm.call("hrm.attendance.month", "load_attendance_grid", [periodId]);
            this.state.edits = {};
            this.state.symbolForm = null;
        } finally {
            this.state.busy = false;
        }
    }

    changePeriod(event) {
        this.state.message = "";
        this.state.batchId = false;
        return this.load(Number(event.target.value));
    }

    get visibleRows() {
        const query = this.state.employeeQuery.trim().toLocaleLowerCase("vi");
        return this.state.grid.rows.filter((row) => `${row.code} ${row.name}`.toLocaleLowerCase("vi").includes(query));
    }

    key(row, day) {
        return row.id + ":" + day;
    }

    editable(row, day) {
        return !this.state.grid.locked && !row.cells[day]?.imported &&
            (!row.start || day >= row.start) && (!row.end || day <= row.end);
    }

    code(row, day) {
        return this.state.edits[this.key(row, day)]?.code ?? row.cells[day]?.code ?? "";
    }

    setCell(row, day, value) {
        const code = value.trim().toUpperCase();
        const key = this.key(row, day);
        const cell = row.cells[day];
        if (code === (cell?.code || "")) {
            delete this.state.edits[key];
        } else {
            this.state.edits[key] = { employee_id: row.id, date: day, revision: cell?.revision || 0, code };
        }
    }

    onInput(row, day, event) {
        this.setCell(row, day, event.target.value);
    }

    unknownCode(row, day) {
        const code = this.state.edits[this.key(row, day)]?.code;
        return code && !Object.hasOwn(this.state.grid.symbols, code) ? code : "";
    }

    openSymbol(operation, code = "") {
        const [regular, overtime] = this.state.grid.symbols[code] || [0, 0];
        this.state.symbolForm = { operation, code, regular, overtime };
        this.state.message = "";
    }

    async submitSymbol(event) {
        event.preventDefault();
        const form = this.state.symbolForm;
        if (this.state.busy || !form) {
            return;
        }
        this.state.busy = true;
        try {
            this.state.grid.symbols = await this.orm.call("hrm.attendance.month", "update_grid_symbol", [
                this.state.grid.period_id, form.operation, form.code, Number(form.regular), Number(form.overtime),
            ]);
            this.state.symbolForm = null;
            this.state.error = false;
            this.state.message = form.operation === "delete" ? "Đã bỏ ký hiệu khỏi danh mục." : "Đã lưu ký hiệu chấm công.";
        } catch (error) {
            this.state.error = true;
            this.state.message = error.data?.message || error.message;
        } finally {
            this.state.busy = false;
        }
    }

    onPaste(row, day, event) {
        const text = event.clipboardData.getData("text");
        if (!/[\t\n]/.test(text)) {
            return;
        }
        event.preventDefault();
        const { rows, dates } = this.state.grid;
        const top = rows.findIndex((candidate) => candidate.id === row.id);
        const left = dates.findIndex((date) => date.key === day);
        const cells = text.replace(/\r/g, "").replace(/\n$/, "").split("\n").map((line) => line.split("\t"));
        const targets = [];
        for (const [y, values] of cells.entries()) {
            for (const [x, value] of values.entries()) {
                const target = rows[top + y];
                const date = dates[left + x]?.key;
                if (!target || !date || !this.editable(target, date)) {
                    this.state.error = true;
                    this.state.message = "Vùng dán có ô khóa hoặc vượt phạm vi bảng.";
                    return;
                }
                targets.push([target, date, value]);
            }
        }
        for (const target of targets) {
            this.setCell(...target);
        }
    }

    total(row) {
        let regular = 0;
        let overtime = 0;
        for (const day of this.state.grid.dates) {
            const edit = this.state.edits[this.key(row, day.key)];
            const cell = row.cells[day.key];
            const hours = edit ? this.state.grid.symbols[edit.code || "0"] : [cell?.regular || 0, cell?.overtime || 0];
            regular += hours?.[0] || 0;
            overtime += hours?.[1] || 0;
        }
        return { regular, overtime, total: regular + overtime, days: regular / (this.state.grid.hours_per_day || 1) };
    }

    fmt(value) {
        return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
    }

    async save() {
        const changes = Object.values(this.state.edits);
        this.state.message = "";
        this.state.batchId = false;
        const invalid = changes.find((edit) => !Object.hasOwn(this.state.grid.symbols, edit.code || "0"));
        if (invalid) {
            this.state.error = true;
            this.state.message = "Ký hiệu chưa được cấu hình: " + invalid.code;
            return;
        }
        this.state.busy = true;
        try {
            const result = await this.orm.call("hrm.attendance.month", "save_attendance_grid", [this.state.grid.period_id, changes]);
            this.state.batchId = result.batch_id;
            this.state.error = !result.ok;
            this.state.message = result.ok ? "Đã lưu " + changes.length + " ô chấm công." : result.message;
            if (result.ok) {
                await this.load(this.state.grid.period_id);
            }
        } catch (error) {
            this.state.error = true;
            this.state.message = error.data?.message || error.message;
        } finally {
            this.state.busy = false;
        }
    }

    openLog() {
        return this.action.doAction({ type: "ir.actions.act_window", res_model: "hrm.import.batch",
            res_id: this.state.batchId, views: [[false, "form"]], target: "current" });
    }

    openSalaryGrid() {
        return this.action.doAction("hrm_data_import.action_salary_month_grid", {
            additionalContext: { salary_grid_period_id: this.state.grid.period_id },
        });
    }

    async setLock(locked) {
        if (this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const periodId = this.state.grid.period_id;
            await this.orm.call("hrm.attendance.month", "set_grid_lock", [periodId, locked]);
            await this.load(periodId);
            this.state.error = false;
            this.state.message = locked ? "Đã khóa nhập công." : "Đã mở khóa. Bạn có thể sửa công.";
        } catch (error) {
            this.state.error = true;
            this.state.message = error.data?.message || error.message;
        } finally {
            this.state.busy = false;
        }
    }
}

registry.category("actions").add("hrm_attendance_grid", AttendanceGrid);

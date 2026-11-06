import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";
import { formView } from "@web/views/form/form_view";

class AllowanceTypeFormController extends FormController {
    setup() {
        super.setup();
        this.notification = useService("notification");
    }

    async onWillSaveRecord(record, changes) {
        this.creatingAllowance = record.isNew;
        return super.onWillSaveRecord(record, changes);
    }

    async onRecordSaved(record, changes) {
        await super.onRecordSaved(record, changes);
        if (this.creatingAllowance) {
            this.creatingAllowance = false;
            this.notification.add(record.data.name, {
                title: _t("Allowance type created"),
                type: "success",
            });
        }
    }
}

registry.category("views").add("hrm_allowance_type_form", {
    ...formView,
    Controller: AllowanceTypeFormController,
});

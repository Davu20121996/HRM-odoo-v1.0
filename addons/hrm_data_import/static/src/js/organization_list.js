import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { ListController } from "@web/views/list/list_controller";
import { listView } from "@web/views/list/list_view";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";

class OrganizationListController extends ListController {
    async createRecord({ group } = {}) {
        const list = group?.list || this.model.root;
        this.dialogService.add(FormViewDialog, {
            resModel: this.props.resModel,
            context: list.context,
            size: "md",
            title: _t("New"),
            onRecordSaved: () => this.model.root.load(),
        });
    }
}

registry.category("views").add("hrm_organization_list", {
    ...listView,
    Controller: OrganizationListController,
});

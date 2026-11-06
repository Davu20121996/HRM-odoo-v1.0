# 02. SMBPlus HRM — Hướng dẫn bàn giao kỹ thuật

**Ngày đối chiếu** · 06/11/2026.  
**Đối tượng** · Dev bảo trì, quản trị môi trường và người tiếp nhận triển khai.  
**Tài liệu đi kèm** · [01 — Vòng đời dữ liệu và testcase](01_VONG_DOI_DU_LIEU_VA_TESTCASE.md).  
**Cách đọc** · Đường dẫn trong tài liệu tính từ thư mục gốc repo. Dùng tên kỹ thuật và XML ID để tìm trên mọi môi trường. ID số của giao diện chỉ đúng với cơ sở dữ liệu đã tạo nó.

## 1. Cấu trúc và môi trường đang chạy

| Thành phần | Vị trí và vai trò |
|---|---|
| Web | Odoo 20 trên Docker, host 8069, [trang đăng nhập](http://localhost:8069/web/login). |
| PostgreSQL | Service `db`, PostgreSQL 16. Odoo kết nối qua mạng Docker nội bộ. |
| Database đang phục vụ | `hrm_smbplus_stage_20261106`. Đọc `db_name` và `dbfilter` trong `config/odoo.conf` trước mọi lệnh. Database cũ `hrm` được giữ riêng. |
| Lưu trữ | DB nằm trong volume Postgres. Filestore nằm trong volume Odoo theo tên DB. Tệp nhị phân có thể cần cả DB và filestore để khôi phục. |
| Điểm nối | `docker-compose.yml` gắn `addons` vào `/mnt/extra-addons` và gắn `config/odoo.conf` vào `/etc/odoo/odoo.conf`. `odoo.conf` ở gốc không phải tệp Compose đang gắn. |
| Module đang cài | `hrm_base`, `hrm_employee`, `hrm_time`, `hrm_payroll`, `hrm_workflow`, `hrm_data_import`. Các addon khác trong repo cần xác minh đã cài trước khi thao tác. |
| Mã tích hợp nghiệp vụ | `addons/hrm_data_import` chứa các mở rộng từ hồ sơ, công, nhập file đến bảng lương. Model gốc có thể nằm ở addon khác. |
| Dữ liệu demo | `addons/hrm_data_import/scripts/setup_smbplus_demo.py` nạp VP, cấu hình và hai kỳ. Script chỉ chạy với database demo mới đúng tên và chưa có công ty. Dùng để truy nguồn, không chạy lại trên DB đang có dữ liệu. |

### Khởi động, reload và upgrade

Chạy từ gốc repo. Dùng Bash cho các script `.sh`. PowerShell chạy được các lệnh Docker dưới đây.

```powershell
docker compose ps
docker compose logs --tail 150 odoo
docker compose logs --tail 100 db
docker compose exec -T db pg_isready -U odoo -d hrm_smbplus_stage_20261106
```

| Thay đổi | Cách áp dụng |
|---|---|
| Lần đầu, Docker Desktop đã chạy | `bash setup.sh`. Kiểm tra service và truy cập web. |
| Chỉ đổi Python, JS hoặc file trong thư mục gắn và không đổi schema/record XML | `bash reload.sh`. Tải lại trang, bật chế độ asset debug để kiểm tra JS. |
| Thêm field, đổi constraint, sửa menu/view XML, quyền, dữ liệu XML hoặc bản dịch | Upgrade đúng module trên bản sao trước. Restart riêng không cập nhật record XML đã lưu trong DB. |
| Đổi Dockerfile hoặc phụ thuộc hệ thống/Python | `bash refresh.sh`. Script dựng lại Odoo và giữ volume. Nếu có thay đổi schema, chạy thêm upgrade. |

Mẫu nâng cấp trên **DB thử nghiệm đã được chuẩn bị**. Dùng biến riêng và xem giá trị trước khi chạy. Nếu dừng Odoo trên môi trường dùng chung thì làm trong cửa sổ bảo trì.

```powershell
$hrmTargetDb = 'hrm_test'
docker compose stop odoo
try {
  docker compose run --rm -T --no-deps odoo odoo -c /etc/odoo/odoo.conf -d $hrmTargetDb -u hrm_data_import --without-demo --stop-after-init --no-http
  if ($LASTEXITCODE -ne 0) { throw 'Upgrade Odoo thất bại' }
} finally {
  docker compose up -d --no-deps --no-build odoo
}
```

Nếu đổi view/model gốc thuộc module khác, thêm module sở hữu vào danh sách `-u`, chẳng hạn `hrm_employee,hrm_data_import`. Kiểm tra lại cột, danh sách, quyền, chuyển trạng thái và export sau nâng cấp.

## 2. Truy từ màn hình đến mã nguồn

1. Bật chế độ nhà phát triển bằng `/odoo?debug=1`. Khi cần tìm file giao diện, mở với `?debug=assets`. Lấy tên action, model, XML ID, tên field và id bản ghi từ màn hình. Ghi lại công ty, kỳ và tài khoản đang sử dụng.
2. URL có `action-295` là action số của DB. Tìm XML ID trong menu kỹ thuật hoặc truy `ir_model_data` theo action, sau đó tìm đúng XML ID trong repo.
3. View Odoo thường kế thừa. Truy cả view gốc và các view có `inherit_id`. XPath dùng tên field, page hoặc button ổn định. Nếu view hợp thành lỗi, đọc log upgrade để lấy XML ID, tên file, dòng và model.
4. Với nút `type="object"`, giá trị `name` là tên method Python. Với `type="action"`, lần theo XML ID action. Với `ir.actions.client`, tìm tag trong registry JS rồi lấy template, method ORM và SCSS/CSS nếu có.
5. Trong DevTools → Network, xem `call_button` hoặc `call_kw` để thấy model/method và lỗi trả về. So khớp thời điểm trong `docker compose logs odoo`. Không chép payload có CCCD, tài khoản ngân hàng hoặc thông tin cá nhân vào báo cáo.
6. Model có thể có nhiều lớp `_inherit`. Xem `__init__.py`, thứ tự nạp và tất cả override của method. Lần theo `super()` trước khi sửa để giữ các bước kiểm tra, audit và bảo hiểm.

```powershell
rg -n 'action_attendance_grid|action_salary_month_grid|action_assignment_popup' addons
rg -n 'action_quick_payroll|def _active_salary|def action_calculate' addons
rg -n 'hrm_employee_assignment|hrm.employee.assignment' addons -g '*.py' -g '*.xml'
rg -n 'salary_grid_calculation|TAXABLE_GROSS|OVERTIME_HOURS' addons
```

### Bản đồ theo chức năng

| Màn hình hoặc lỗi | File ưu tiên và điểm vào |
|---|---|
| Menu tách theo ứng dụng | `addons/hrm_data_import/views/app_navigation.xml`. Kiểm tra parent, sequence, action và groups. |
| Doanh nghiệp, popup phòng ban | `views/quick_entry_views.xml`, `models/quick_entry.py`, `static/src/js/organization_list.js` trong addon nhập. Model gốc ở `addons/hrm_base/models/organization.py`. |
| Hồ sơ, bằng cấp, ảnh, tài liệu | `views/employee_complete_views.xml`, `views/employee_entry_views.xml`, `models/employee_entry.py`. Model gốc `addons/hrm_employee/models/employee.py`. |
| Phân công, lịch sử, nghỉ việc và kích hoạt lại | `views/employee_assignment_views.xml`, `models/employee_assignment.py`. Truy `action_assignment_popup`, `action_apply`, `action_reactivate_employee`, `_primary_assignments`. |
| Hợp đồng, Tái ký và nhóm trạng thái | `views/employee_entry_views.xml`, `models/employee_entry.py`, `models/business_flow.py`, `addons/hrm_employee/models/employment.py`. Truy `action_renew_from_contract`, `action_activate`, `write` và ba trường one2many nhóm. |
| Phụ cấp | `views/allowance_views.xml`, `models/allowances.py`, `static/src/js/allowance_type_form.js`. Truy `_policy_at`, `_split`, `_check_editable`, `_additional_earnings`. |
| Nhập nhân viên VP | `models/hr_workspace.py`, `views/hr_workspace_views.xml`. Kiểm tra mapping, preview, cột ngày Excel và trạng thái tiếng Việt. |
| Mapping, preview, commit công/KPI | `models/imports.py`, `engine.py`, `views/import_views.xml`, `views/import_workflow_views.xml`. Truy `_lock_scope`, `_validate_row`, `_decision`, `action_preview`, `action_commit`. |
| Bảng công nhập ô | `views/attendance_grid_views.xml`, `static/src/js/attendance_grid.js`, `static/src/xml/attendance_grid.xml`, `models/attendance_grid.py`. API `load_attendance_grid`, `save_attendance_grid`, `update_grid_symbol`, `set_grid_lock`. |
| Báo cáo công lịch sử | `models/timesheet_report.py`, `views/timesheet_report_views.xml`. SQL view theo kỳ/nhân viên và theo từng nguồn/ngày. |
| Bảng lương nhập ô | `views/salary_grid_views.xml`, `static/src/js/salary_grid.js`, `static/src/xml/salary_grid.xml`, `models/salary_grid.py`. API `load_salary_grid`, `update_salary_grid`. |
| Bảng lương Excel, điều chỉnh, xuất | `models/salary_quick.py`, `models/salary_columns.json`, `views/salary_quick_views.xml`. Truy `_excel_values`, `_salary_xlsx`, `excel_expression`, `restore_formula`. |
| Quy trình tính, công thức và bảo hiểm | `addons/hrm_payroll/models/run.py`, cùng `models/hr_workspace.py`, `business_flow.py`, `formulas.py`, `insurance.py`, `allowances.py` trong addon nhập. |
| Biểu mẫu phiếu, hợp đồng in | `views/business_flow_views.xml`, `views/print_reports.xml`, `views/allowance_views.xml`. Kiểm tra dữ liệu nguồn ở item và payslip trước khi sửa QWeb. |
| Phân quyền, ngôn ngữ | `security/access.xml`, `security/company_scope.xml`, `security/workspace_access.xml`, các record quyền trong XML tính năng, `models/company_scope.py`, `models/ui_language.py`, `i18n/vi.po`, `i18n/hrm_data_import.pot`. |

Các mục ghi `models/`, `views/`, `static/`, `security/` hoặc `i18n/` mà không ghi tên addon thuộc `addons/hrm_data_import`.

## 3. Xem dữ liệu và đối chiếu log

### SQL đọc trên demo

```powershell
$hrmDemoDb = 'hrm_smbplus_stage_20261106'
docker compose exec -T db psql -U odoo -d $hrmDemoDb -c "SELECT current_database(); SELECT id,code,name FROM hrm_company;"
docker compose exec -T db psql -U odoo -d $hrmDemoDb -c "SELECT module,name,model,res_id FROM ir_model_data WHERE name IN ('action_attendance_grid','action_salary_month_grid');"
docker compose exec -T db psql -U odoo -d $hrmDemoDb -c "SELECT p.period_code,i.dataset,count(*) FROM hrm_import_input i JOIN hrm_payroll_period p ON p.id=i.period_id GROUP BY p.period_code,i.dataset ORDER BY 1,2;"
docker compose exec -T db psql -U odoo -d $hrmDemoDb -c "SELECT employee_id,company_id,count(*) FROM hrm_employee_contract WHERE status='active' GROUP BY employee_id,company_id HAVING count(*)>1;"
```

Tách ba khóa khi điều tra. **Công ty** xác định phạm vi. **Kỳ** xác định khoảng ngày. **Nhân viên** xác định dữ liệu và lần tính. Truy công từ `hrm_import_input.payload` với `work_date`, `regular_hours`, `overtime_hours`, `attendance_symbol`, `revision` và `batch_id`. Truy lương từ `hrm_payroll_period → hrm_payroll → hrm_payroll_item`; dòng chi tiết nằm ở `hrm_payslip_item` theo bảng lương và nhân viên. Lịch sử sửa phân công nằm ở `hrm_employee_assignment_log`.

### Odoo shell đọc dữ liệu

```powershell
docker compose exec odoo odoo shell -c /etc/odoo/odoo.conf -d hrm_smbplus_stage_20261106 --no-http
```

```python
user = env.ref('base.user_admin')
periods = env['hrm.payroll.period'].with_user(user).search([])
periods.read(['period_code', 'status', 'company_id', 'standard_days'])
period = periods.filtered(lambda row: row.period_code == '2026-10')
grid = env['hrm.payroll.period'].with_user(user).load_salary_grid(period.id)
len(grid['rows'])
env.cr.rollback()
```

Dùng `with_user` để tái hiện quyền người dùng. `sudo()` chỉ phục vụ điều tra có kiểm soát và không dùng làm cách sửa lỗi quyền. Với dữ liệu cần chỉnh, ưu tiên method nghiệp vụ trong bản sao vì chúng tạo lịch sử, thực thi khóa và cập nhật các bảng liên quan. Kết thúc phiên đọc bằng rollback.

## 4. Sửa model, view và dữ liệu có kiểm soát

### A. Thêm hoặc sửa field trên model đã có

1. Tìm model gốc và tất cả phần kế thừa. Đặt field trong addon sở hữu quy tắc. Với phần SMBPlus, thường dùng `_inherit = 'hrm.employee.contract'` hoặc model liên quan trong `hrm_data_import`.
2. Chọn kiểu và vòng đời. `Many2one` cần quyết định `ondelete`, domain và công ty. Trường compute cần `@api.depends` phù hợp. Dùng `store=True` khi cần tìm kiếm/tổng hợp, và có kế hoạch cập nhật bản ghi cũ. Tránh thêm cột bắt buộc khi dữ liệu cũ chưa có giá trị.
3. Domain UI giúp chọn dữ liệu đúng. Quy tắc bắt buộc cần kiểm tra phía máy chủ trong constraint hoặc method ghi. So khớp nhân viên, công ty và đơn vị quản lý trước khi lấy dữ liệu.
4. Đăng ký tệp trong `models/__init__.py` nếu thêm tệp Python. Thêm dependency vào manifest nếu module cần model của addon khác. Với model mới, thêm quyền theo nhóm, rule công ty, view và menu nếu nghiệp vụ cần.
5. Đổi field hoặc đổi ý nghĩa của dữ liệu có sẵn phải lập migration rõ điều kiện trước/sau, xử lý bản ghi chưa có giá trị và kiểm tra chạy lại. Upgrade bản sao trước và so sánh số bản ghi, lỗi SQL, kết quả cũ/mới.
6. Dữ liệu hiệu lực theo ngày hoặc đã duyệt dùng bản điều chỉnh hoặc phiên bản mới. Khi sửa luồng hợp đồng, kiểm tra kích hoạt mới đóng đúng bản cũ, ngày bao phủ kỳ và phụ cấp kế thừa. Khi sửa luồng công, giữ id nguồn và revision.

Ví dụ thêm trường ghi chú nội bộ. Quyền đọc trường cần được xét nếu trường chứa thông tin nhạy cảm.

```python
from odoo import fields, models

class Contract(models.Model):
    _inherit = 'hrm.employee.contract'

    hrm_internal_note = fields.Text(string='Internal note')
```

### B. Sửa giao diện

1. Sửa đúng inherited view, giữ XML ID ổn định. Ví dụ chèn field sau lương cơ bản trong form hợp đồng.
2. Với các trạng thái, dùng biểu thức `invisible`, `readonly`, `required` theo quy tắc hiện hành. Field dùng trong biểu thức cần có trên view. Với x2many, kiểm tra cả popup dòng mới, dòng đã lưu và dialog trạng thái.
3. Thêm tệp view mới vào `data` của manifest sau dependency. Tệp OWL/JS vào `web.assets_backend`. Odoo 20 hiện dùng Owl với `proxy` và `useProps` theo cấu hình của repo. Lấy bảng công/lương làm mẫu.
4. Nâng cấp XML. Mở lại web, thử với tài khoản nhập liệu và tài khoản duyệt. Thử bản nháp và bản đã khóa, tiếng Việt và tiếng Anh nếu phần đó đã có bản dịch.

```xml
<field name="base_salary" position="after">
  <field name="hrm_internal_note"/>
</field>
```

### C. Sửa lương và nhập liệu

- **Sai số công** · Mở đúng kỳ và log batch. Kiểm tra dữ liệu theo ngày, giờ thường, tăng ca, trùng nguồn, revision. Nếu nguồn là file thì sửa file, không cộng thêm ô mới vào ngày đã có. Tính lương đọc giờ thường và giờ tăng ca riêng.
- **Sai nguồn lương cơ bản** · Truy `_active_salary` và log `contract_salary_source`. Phải có một hồ sơ hiệu lực bao phủ kỳ. Kiểm tra cấu hình lương đóng bảo hiểm và cơ cấu. Đổi lương hợp đồng qua hồ sơ mới phù hợp.
- **Sai số phụ cấp/thuế** · So giá trị từng dòng hợp đồng, mức miễn theo ngày, phần chịu thuế, `TAXABLE_GROSS`, khoản thuế và số thực nhận. Cấu hình demo không đủ để kết luận công thức chuẩn doanh nghiệp. Khi thay công thức thật, lấy bản Excel còn nguyên công thức và dữ liệu mẫu đã duyệt.
- **Sai số một ô lương** · So `hrm.salary.adjustment` theo mã khoản và kỳ. Bản duyệt mới nhất ghi đè. Bản có `restore_formula` đưa ô về cách tính tự động. Luồng bảng lương ưu tiên công thức được duyệt khi có. Số hiệu quả có thể đi thẳng vào khoản được ánh xạ khi không có công thức thay thế.
- **Sai tổng hoặc xuất Excel** · So `gross_amount - deduction_amount - tax_amount = net_amount`. Khấu trừ đã gồm bảo hiểm người lao động. Không trừ phần công ty vào thực nhận. So dữ liệu A–AZ và sheet log; thay header phải đồng bộ code cột, bản dịch, UI và testcase.
- **Sai khóa** · Bắt đầu tại `_grid_lock_mode`, `update_salary_grid`, `_lock_scope` và `action_reopen_inputs`. Khi mở lương, hệ thống lưu kết quả trước vào log và tính lại sau. Khóa công riêng vẫn có thể tồn tại. Kỳ đã duyệt/chốt không dùng luồng mở lại.
- **Thay đổi đồng thời** · Giữ thứ tự khóa kỳ hoặc nhân viên/hợp đồng, kiểm tra trạng thái sau khóa. Dùng khóa nguồn và revision. Hành động batch dùng savepoint để tránh ghi dở. Khi bổ sung một đường sửa mới, áp dụng cùng điều kiện khóa và audit ở server.

## 5. Kiểm thử, nghiệm thu triển khai và khôi phục

- Chạy các ca kiểm thử của `addons/hrm_data_import/tests/test_import.py`, `test_workspace.py`, `test_company_scope.py`. Bộ bàn giao gần nhất đạt 28/28. Môi trường test mới cần cài tiếng Việt để chạy ca nhãn giao diện.
- Sau upgrade, kiểm tra bằng hai tài khoản khác công ty, trường hợp bản ghi cũ thiếu dữ liệu, dữ liệu nháp/đã duyệt, lỗi nguồn và thao tác đồng thời. Với UI, mở đường đi thật từ menu. Kiểm tra màn hình web và file xuất trên cùng lần tính.
- Đối chiếu bộ [testcase nghiệp vụ](01_VONG_DOI_DU_LIEU_VA_TESTCASE.md). Thu ảnh trạng thái, báo lỗi, batch/revision và số liệu tổng hợp, đã che trường nhạy cảm.
- Sao lưu DB và filestore đúng tên DB trước migration. Với PostgreSQL dump, dùng `pg_dump -Fc -f` trong container rồi `docker compose cp` ra vùng backup. Tránh chuyển dump nhị phân qua phép chuyển hướng văn bản của PowerShell. Kiểm tra dump bằng `pg_restore -l`. Kiểm tra quyền đọc và khả năng khôi phục bằng bản sao.
- Nếu bản phát hành lỗi, ưu tiên dừng phát hành và khôi phục trên DB khác trước. DB và filestore phải là cặp cùng thời điểm. Khi cần đổi DB đang phục vụ, cập nhật cả `db_name` và `dbfilter`, khởi động lại, kiểm tra đăng nhập, số công ty, tháng và quyền.
- Sau bàn giao, quyền demo và mật khẩu quản trị do người tiếp nhận quản lý. Tài liệu không chứa mật khẩu môi trường.

```powershell
$hrmTargetDb = 'hrm_test'
docker compose run --rm -T --no-deps odoo odoo -c /etc/odoo/odoo.conf -d $hrmTargetDb -u hrm_data_import --without-demo --stop-after-init --test-enable --test-tags /hrm_data_import --no-http --log-level=test
```

## 6. Cây chẩn đoán nhanh

| Dấu hiệu | Kiểm tra trước |
|---|---|
| Vẫn thấy UI cũ | Đúng DB và action chưa, module đã upgrade chưa, asset cũ còn lưu không. |
| Không thấy nút | Trạng thái bản ghi, groups, domain công ty, view kế thừa áp dụng. |
| Phân công không hiện | Phân công chính, công ty, ngày hiệu lực, trạng thái nhân viên và bộ lọc cuối kỳ. |
| Sửa ô công bị chặn | Khóa lương, khóa riêng công, nguồn import, ngày hợp lệ, revision. |
| Import báo dữ liệu trùng | Cùng nhân viên, kỳ, nguồn, khóa nguồn và revision. Đọc normalized/previous của dòng log. |
| Chưa tính được lương | Hợp đồng hiệu lực, bao phủ kỳ, cơ cấu, công chuẩn, KPI bắt buộc, log `calculation_failed`. |
| Bản tái ký ở sai nhóm | So `status`, `parent_id` và nhóm one2many. Kiểm tra form cha tải lại sau chuyển trạng thái. |
| Đổi chính sách mà kỳ cũ khác | So snapshot phiên bản hiệu lực, trạng thái khóa, lần tính, bản phụ cấp dùng trong kỳ. |
| Xuất Excel lệch web | Kiểm tra cùng công ty/kỳ, lần tính, snapshot bảo hiểm và ánh xạ A–AZ. |
| Odoo trả lỗi AccessError | Tái hiện đúng người dùng, xác minh rule `hrm_company_ids` và quyền model/action. |

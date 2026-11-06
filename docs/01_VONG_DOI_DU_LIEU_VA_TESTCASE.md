# 01. SMBPlus HRM — Vòng đời dữ liệu và bộ testcase bàn giao

**Phạm vi** · Odoo 20, dữ liệu demo SMBPlus, kỳ 09 và 10/2026.  
**Ngày đối chiếu** · 06/11/2026.  
**Đối tượng** · Quản lý nghiệp vụ, nhân sự, tester và người nghiệm thu.  
**Tài liệu đi kèm** · [02 — Hướng dẫn kỹ thuật](02_HUONG_DAN_DEV.md).

## 1. Bắt đầu nghiệm thu

| Điểm vào | Dữ liệu chuẩn để đối chiếu |
|---|---|
| [Trang đăng nhập](http://localhost:8069/web/login) | Dùng tài khoản demo do người quản trị bàn giao. Kiểm tra thấy công ty SMBPlus sau khi đăng nhập. |
| Nhân viên → Hồ sơ nhân viên | 26 hồ sơ VP, gồm 21 đang làm và 5 đã nghỉ. Hợp đồng gồm 21 đang hiệu lực, 5 đã đóng. |
| Doanh nghiệp → Phòng ban | Maketting, IT, IT dev và IT helpdesk trực thuộc IT, CSKH, Kế toán. |
| [Bảng nhập công theo tháng](http://localhost:8069/odoo/action-295) | Hai kỳ 09 và 10/2026. Tổng 924 dòng công, 462 dòng mỗi kỳ. Mỗi kỳ có 8 nhân viên IT × 30 giờ tăng ca. |
| [Bảng nhập lương theo tháng](http://localhost:8069/odoo/action-296) | 21 kết quả mỗi kỳ, 10 dòng KPI nhập cho hai tháng. Hai kỳ ở trạng thái đã tính tại thời điểm bàn giao. |
| Quản trị nhân sự → Log nhập và lương | Có log theo đợt và lịch sử tính. Log phân công xem trực tiếp trong hồ sơ nhân viên. |

Các ca làm thay đổi hồ sơ, công và lương chạy trên bản sao. Với mỗi ca, ghi mã ca, phiên bản, kỳ, mã nhân viên, người thao tác, kết quả thực tế và bằng chứng. Dùng trạng thái **Đạt**, **Không đạt**, **Bị chặn** hoặc **Chưa chạy**. Các bước dưới đây là kịch bản nghiệm thu thủ công. Bộ kiểm thử tự động gần nhất chạy **28 ca đạt, 0 lỗi** trên cơ sở demo sau khi nạp dữ liệu. Báo cáo này tách kết quả tự động khỏi các ca thủ công chưa thực hiện.

## 2. Vòng đời nghiệp vụ

1. **Thiết lập** · Tạo công ty và đơn vị quản lý. Tạo cây phòng ban, chức danh, vị trí, dự án, loại hợp đồng và chính sách phụ cấp.
2. **Hồ sơ** · Tạo hoặc nhập sheet VP. Mã nhân viên là khóa đối chiếu theo đơn vị quản lý. Mở **Phân công** để gán phòng ban, chức vụ thuộc phòng ban và dự án. Khi sửa phân công, nhập lý do và đối chiếu người nhập trước, người sửa, giá trị trước/sau.
3. **Hợp đồng** · Bản nháp → Chờ duyệt → Đã duyệt, chờ kích hoạt → Đang có hiệu lực → Đã đóng. Bản tái ký bắt đầu ở bản nháp và lưu hợp đồng gốc. Kích hoạt bản mới chuyển bản cũ sang lịch sử. Chỉ một hồ sơ hiệu lực được dùng để tính lương và hồ sơ đó phải bao phủ kỳ.
4. **Đầu vào tháng** · Tạo kỳ đúng công ty, khoảng ngày, công chuẩn và giờ chuẩn. Chuẩn bị mapping. Xem trước → sửa lỗi nguồn → ghi đợt. Excel nghiệp vụ cấp công và tiền hiệu quả. Các dữ liệu lương cơ bản, phụ cấp lấy từ hợp đồng, còn điều chỉnh cá biệt thực hiện trên bảng lương có lý do.
5. **Chấm công** · Chọn kỳ, xem tất cả nhân viên của công ty. Có thể chấm theo ô hoặc nhập file. Dòng đã nhập từ nguồn khác được xem trên lưới và sửa qua đúng nguồn. Khi sửa từ file, giữ khóa nguồn và tăng phiên bản. Tổng giờ thường và giờ tăng ca tách riêng.
6. **Tính và điều chỉnh** · Kiểm tra dữ liệu kỳ. Tính lương theo công thức, đọc lương hợp đồng, phụ cấp, công, hiệu quả và bảo hiểm. Nhập tay một khoản và lưu lý do nếu cần thay thế. Xóa giá trị nhập tay rồi lưu để trở về cơ chế tự động.
7. **Khóa, duyệt, chốt** · Khóa lương với lý do sẽ tính và khóa công cùng kỳ. Kỳ đã tính nhưng chưa duyệt có thể mở lại từ bảng lương với lý do. Kết quả trước đó được lưu log, sau sửa phải tính lại. Nếu công đã khóa riêng, mở khóa công sau bước mở lương. Kỳ đã duyệt, chốt hoặc thanh toán giữ ở chế độ xem. Phiếu lương chính thức phát sinh khi chốt.
8. **Đối soát** · Bảng lương web và file Excel kiểm tra theo từng mã nhân viên, kỳ và lần tính. Sheet Luong giữ mẫu 52 cột, sheet CongThuc_Log lưu dòng thành phần và công thức. Luôn lấy kỳ và lần tính làm khóa đối chiếu.

## 3. Ma trận thêm, sửa, xóa theo model nghiệp vụ

Cột **Xóa** mô tả thao tác nghiệp vụ có chủ đích. Quyền thực tế còn phụ thuộc vai trò, trạng thái, khóa ngoại và công ty. Với lịch sử, chuyển trạng thái hoặc ghi phiên bản thay thế là cách sửa dữ liệu.

| Model | Thêm | Sửa | Xóa, kết thúc và truy vết |
|---|---|---|---|
| `hrm.tenant` | Tạo đơn vị quản lý trước công ty | Sửa thông tin đơn vị trong phạm vi được cấp | Kiểm tra phụ thuộc trước khi dọn cấu hình. Không dùng để làm sạch dữ liệu một kỳ. |
| `hrm.company` | Tạo từ Doanh nghiệp, gắn đơn vị quản lý | Cập nhật thông tin doanh nghiệp | Chủ sở hữu phạm vi được xác định từ người tạo. Dùng cơ sở demo mới cho reset hàng loạt. |
| `hrm.department` | Tạo phòng ban và chọn cha cùng công ty | Đổi tên, cơ cấu hoặc trạng thái | Tránh xóa phòng ban đã được tham chiếu. Kiểm tra không tạo vòng cha–con. |
| `hrm.business.unit`, `hrm.location`, `hrm.cost.center` | Tạo danh mục công ty trong thiết lập tổ chức | Sửa mã, tên, quan hệ theo ràng buộc | Đóng/lưu trữ nếu đã dùng. Kiểm tra tham chiếu trước khi xóa. |
| `hrm.job`, `hrm.position`, `hrm.grade` | Tạo chức danh/vị trí/bậc. Vị trí gắn phòng ban và chức danh | Sửa thông tin danh mục trong đúng phạm vi | Lưu trữ vị trí hết dùng. Kiểm tra hồ sơ, phân công đang tham chiếu. |
| `hrm.employee.project` | Tạo từ popup phân công, cùng công ty | Chọn lại dự án trong phân công, kèm lý do | Luồng hiện tại cấp tạo/sửa/xem danh mục. Bỏ dự án khỏi phân công qua popup và ghi lịch sử. |
| `hr.employee`, `hrm.person` | Nhập VP hoặc tạo hồ sơ web | Sửa thông tin hồ sơ, ảnh đại diện, tài liệu lý lịch | Nghỉ việc qua trạng thái. **Kích hoạt lại** trong chi tiết khi quay lại. Tránh xóa cứng hồ sơ có lương hoặc hợp đồng. |
| `hrm.employee.education`, `hrm.employee.certification`, `hrm.employee.document` | Thêm bằng cấp, chứng nhận, hồ sơ theo quyền | Sửa metadata hoặc thay tệp phù hợp | Kiểm tra hồ sơ tham chiếu trước khi xóa. Lý lịch tải PDF hoặc ảnh được hỗ trợ, tối đa 10 MB. |
| `hrm.employee.assignment.wizard` | Bấm **Phân công** để mở popup | Chọn phòng ban, chức vụ, dự án và lý do nếu đã có bản ghi | Popup là dữ liệu tạm. Hủy không lưu phân công. |
| `hrm.employee.assignment` | Lưu phân công lần đầu từ popup | Yêu cầu lý do ở popup nếu sửa. Nhân viên nghỉ việc không được phân công hiệu lực | Model chặn xóa cứng. Giữ dữ liệu lịch sử. |
| `hrm.employee.assignment.log`, `hrm.employment.status.history` | Tự sinh theo thao tác nghiệp vụ | Xem người thực hiện, người nhập trước nếu có, lý do hoặc chuyển trạng thái | Đọc lịch sử trong hồ sơ hoặc màn hình log. Không sửa log qua UI. |
| `hrm.contract.type` | Tạo loại hợp đồng trong danh mục | Sửa tên/cấu hình trước khi áp dụng | Giữ loại đã được hợp đồng tham chiếu. |
| `hrm.employee.contract` | Tạo nháp trống, lấy bản cũ hoặc bấm Tái ký | Sửa nội dung trước khi duyệt. Đổi lương/phụ cấp qua hồ sơ mới phù hợp | Đóng hợp đồng để vào lịch sử. Bản tái ký giữ parent. Hợp đồng đã duyệt/hiệu lực bị chặn xóa cứng. |
| `hrm.allowance.type`, `hrm.allowance.version` | Tạo loại, chế độ thuế, ngưỡng. Thêm phiên bản theo ngày | Đổi chính sách bằng phiên bản, có lý do | Phiên bản đã lưu giữ nguyên. Không xóa phiên bản lịch sử. |
| `hrm.contract.allowance` | Thêm dòng loại phụ cấp và số tiền dưới lương cơ bản | Bấm dòng để sửa trong hồ sơ chưa duyệt | Xóa dòng khi hồ sơ còn sửa được. Với hồ sơ đã duyệt, tạo phụ lục hoặc hợp đồng mới phù hợp. |
| `hrm.employee.import`, `hrm.employee.import.column` | Tạo lượt import VP và ánh xạ cột | Kiểm tra preview, sửa mapping trước khi nhập | Dùng file đã sửa hoặc lượt import mới cho sai sót. Giữ thông tin đối chiếu nguồn. |
| `hrm.import.profile`, `hrm.import.mapping` | Chọn tập dữ liệu và tạo mapping, sau đó duyệt | Sửa bản nháp. Sao chép phiên bản nếu mapping đã duyệt | Giữ mapping đã dùng để đọc log đợt. |
| `hrm.import.batch`, `hrm.import.line` | Tải file, xem trước, kiểm tra từng dòng | Sửa file/mapping rồi xem trước lại khi batch chưa ghi | Batch đã ghi bất biến. Xem log tạo, cập nhật, trùng hoặc lỗi. |
| `hrm.import.input` | Tự tạo từ batch đã ghi hoặc bảng công/luồng nhập trực tiếp | Ghi phiên bản mới cùng khóa nguồn và cao hơn | Dùng revision để truy vết. Công 0 là một giá trị đã ghi, ô trống là thiếu nguồn. |
| `hrm.manual.input` | Tạo dòng công hoặc hiệu quả trực tiếp | Sau khi gửi, tạo dòng mới với mã nguồn và revision tăng | Bản đã gửi giữ để đối chiếu với batch. |
| `hrm.attendance.symbol` | Tạo mã cùng số giờ thường/tăng ca | Chỉnh ngay trên bảng công hoặc trong danh mục | Bỏ mã khỏi danh mục cho lần nhập sau. Giờ đã lưu giữ theo lần nhập. |
| `hrm.attendance.month`, `hrm.attendance.day` | Hệ thống xây báo cáo từ đầu vào theo kỳ | Sửa qua nguồn đầu vào đúng quyền | Báo cáo chỉ đọc. Mở chi tiết ngày để xem nguồn và revision. |
| `hrm.monthly.workspace`, `hrm.monthly.line` | Tạo bộ lọc công ty, tháng, năm hoặc nhân viên | Làm mới bảng để nạp đầu vào và kết quả | Dòng tổng hợp được dựng lại. Dữ liệu nguồn vẫn ở model nghiệp vụ. |
| `hrm.payroll.period` | Tạo kỳ, ngày công chuẩn và giờ/ngày | Sửa khi còn mở. Mở lại có lý do nếu chưa duyệt | Kỳ đã duyệt/chốt/thanh toán chỉ xem. Khóa lương chi phối khóa công. |
| `hrm.salary.structure`, `hrm.salary.component` | Tạo cơ cấu và khoản thu nhập, khấu trừ hoặc thuế | Sửa cấu hình theo chính sách hiệu lực và phạm vi công ty | Lưu trữ cấu hình hết dùng, kiểm tra công thức và hợp đồng tham chiếu. |
| `hrm.payroll.formula` | Tạo nháp, chạy thử, duyệt theo ngày hiệu lực | Tạo phiên bản mới khi đã duyệt | Công thức đã duyệt giữ lịch sử. Tránh ghi đè kỳ đã tính. |
| `hrm.salary.adjustment` | Nhập tay một khoản, ghi lý do và duyệt | Điều chỉnh mới hoặc ghi bản trả về công thức | Bản duyệt không xóa/sửa. Giữ người duyệt và thời điểm. |
| `hrm.payroll`, `hrm.payroll.item` | Tính kỳ, tạo lần tính và kết quả nhân viên | Kỳ chưa duyệt có thể mở lại, log kết quả cũ rồi tính lại | Không xóa kết quả đã duyệt/chốt. So sánh theo lần tính. |
| `hrm.payslip`, `hrm.payslip.item` | Tạo thành phần khi tính, phát hành phiếu khi chốt | Thay đổi đầu vào trong kỳ còn mở, sau đó tính lại | Kết quả chốt giữ lịch sử. Phiếu chính thức phải khớp kết quả kỳ chốt. |
| `hrm.audit.log`, `hrm.demo.workspace`, `hrm.demo.source` | Log tự sinh. Gói demo/tệp nguồn được lập theo công ty khi có | Xem actor, hành động, thời điểm, bản ghi và nguồn | Giới hạn truy cập theo công ty. Không dọn log như dữ liệu nháp. |

## 4. Hướng dẫn sử dụng và nghiệm thu chi tiết theo hạng mục

### 4.1. Chuẩn bị buổi demo và phân vai

1. Mở [Odoo](http://localhost:8069/web/login), đăng nhập bằng tài khoản được bàn giao. Vào **Doanh nghiệp → Thông tin doanh nghiệp** và kiểm tra tên **SMBPlus**.
2. Mở bảng công và bảng lương trong hai tab trình duyệt. Chọn **10/2026** ở cả hai để tránh so chéo kỳ. Dùng **09/2026** để trình diễn lịch sử.
3. Phân hai vai thử nghiệm. Người nhập liệu tạo hồ sơ, nhập công và xem trước file theo quyền. Người duyệt thực hiện duyệt, kích hoạt hợp đồng, sửa chính sách, điều chỉnh và mở khóa lương. Khi cần chứng minh giới hạn công ty, dùng hai tài khoản khác công ty trên bản sao.
4. **Luồng trình bày cho quản lý** · Cơ cấu tổ chức → hồ sơ nhân viên → hợp đồng và phụ cấp → công và KPI → bảng lương → Excel và lịch sử. Dùng dữ liệu có sẵn để xem; các ca ghi mới, xóa, kích hoạt, khóa hoặc chốt chạy trên bản sao.
5. **Dữ liệu thử mới** · Dùng tiền tố `UAT-` cho phòng ban, dự án, mã nhân viên, số hợp đồng và nguồn import. Ghi rõ tháng, nhân viên, tài khoản, mã ca và trạng thái ban đầu trước khi sửa. Đặt lại bản sao sau buổi thử nếu cần chạy lại từ đầu.
6. **Tiêu chí đạt chung** · Thấy đúng công ty, đúng kỳ và nhân viên. Giá trị lưu khớp sau tải lại. Thao tác bị từ chối không làm đổi dữ liệu. Bằng chứng đủ để người khác lặp lại. Chỉ ghi ca là **Đạt** sau khi đã thực hiện.

### 4.2. Doanh nghiệp và cây phòng ban · ENV-01, ORG-01, ORG-02

**Mục tiêu** · Người quản lý thấy cấu trúc SMBPlus, nhân sự thêm phòng ban nhanh và gắn đúng cấp cha.

1. Vào **Doanh nghiệp → Phòng ban**. Tìm **IT**, mở bản ghi và đối chiếu **IT dev** và **IT helpdesk** là cấp con. Mở từng phòng con và kiểm tra trường cha.
2. Trên bản sao, bấm **Mới** từ danh sách hoặc **Thêm phòng ban con** trong chi tiết phòng cha. Nhập tên `UAT-IT Support`. Chọn cha IT nếu đi từ danh sách. Kiểm tra công ty trước khi lưu.
3. Lưu, tìm lại theo tên, mở dòng vừa thêm và sửa tên thử. Lưu rồi tải lại để xác nhận. Nếu đang thử xóa, chọn bản ghi thử chưa được tham chiếu; với phòng ban đã có phân công, kiểm tra tham chiếu và dùng trạng thái lưu trữ phù hợp.
4. Thử chọn chính phòng đó làm cha hoặc tạo quan hệ vòng. Nếu có hai công ty trên bản sao, thử chọn phòng cha từ công ty kia.

**Đạt khi** · Phòng con thuộc đúng SMBPlus và đúng cha; cấu trúc sai bị từ chối. Chụp cây trước/sau và thông báo lỗi nếu có. Nếu không thấy nút **Mới**, kiểm tra quyền và công ty trên tài khoản.

### 4.3. Hồ sơ nhân viên và import VP · EMP-01 đến EMP-04

**Mục tiêu** · Người nhập liệu xem được ánh xạ và kết quả trước khi ghi hồ sơ. Người quản lý phân biệt nhân viên đang làm và đã nghỉ.

1. Vào **Nhân viên → Nhập nhân viên**. Bấm **Mới**, chọn SMBPlus, tải file nhân viên và nhập tên sheet `VP`. Mở tab **Ánh xạ cột**.
2. Kiểm tra các đích tối thiểu `code`, `full_name`, `working_status_id`. So thêm một cột liên hệ hoặc ngày sinh với cột nguồn. File thử dùng mã dạng chữ và cột ngày Excel. Chọn chế độ cập nhật nếu chủ đích là sửa hồ sơ trùng mã.
3. Bấm **Kiểm tra file**, mở phần xem trước và ghi lại số dòng hợp lệ/lỗi. Nếu bị lỗi, sửa file hoặc mapping rồi kiểm tra lại. Bấm **Nhập nhân viên** sau khi đối chiếu.
4. Mở **Nhân viên → Danh sách nhân viên**, tìm mã thử, đối chiếu công ty, tên, tình trạng, liên hệ. Với ca thêm tay, bấm **Mới**, nhập các trường bắt buộc, lưu rồi thêm ảnh đại diện, bằng cấp và lý lịch trong chi tiết.
5. Trên bản sao, mở một hồ sơ đã nghỉ. Xác nhận danh sách không cho **Phân công**. Nếu thử quay lại làm việc, bấm **Kích hoạt lại** trong chi tiết và xác nhận. Quay về danh sách, kiểm tra trạng thái và nút **Phân công**.

**Đạt khi** · Tìm được hồ sơ theo mã sau khi lưu, trạng thái đúng nguồn, thông tin đã cập nhật giữ nguyên sau tải lại. Bằng chứng dùng mã hồ sơ; che CCCD, ngân hàng, điện thoại và ngày sinh khi gửi báo cáo.

### 4.4. Phân công và lịch sử điều chỉnh · ASG-01 đến ASG-03

1. Trong danh sách nhân viên đang làm, bấm **Phân công** ở cuối dòng hoặc mở hồ sơ và bấm nút tương ứng.
2. Chọn **Phòng ban** trước. Chọn **Chức vụ** của phòng đó. Nếu thiếu chức vụ, chọn **Thêm chức vụ mới** và nhập tên. Tại **Dự án**, chọn một hoặc nhiều dự án; dùng **Tạo và chỉnh sửa** nếu cần thêm dự án mới.
3. Bấm **Lưu phân công**, rồi mở tab **Phân công và lịch sử** để so phòng ban, chức vụ, dự án. Mở lại popup, thử đổi dự án và để trống lý do. Sau khi xác nhận hệ thống chặn, điền `UAT-ASG-02 · Chọn nhầm dự án` và lưu.
4. Đối chiếu log gồm thời điểm, người thao tác, người nhập trước, lý do và nội dung trước/sau. Dùng hai phiên trình duyệt trên bản sao nếu thử lưu đồng thời.
5. Mở bảng công và lương đúng kỳ để kiểm tra hai cột **Phòng ban** và **Dự án**. Hai bảng lấy phân công theo cuối kỳ. Nếu dữ liệu chưa hiện, kiểm tra thời gian hiệu lực của phân công.

**Đạt khi** · Chức vụ thuộc phòng đã chọn, thay đổi có lý do và log đầy đủ. Người giữ popup cũ nhận thông báo khi phân công đã đổi.

### 4.5. Hợp đồng, tái ký và một hồ sơ hiệu lực · HD-01 đến HD-04

1. Mở hồ sơ → **Hợp đồng**. Đối chiếu ba nhóm **Đang có hiệu lực**, **Chờ xử lý**, **Lịch sử đã đóng**, và hai cột **Loại**, **Hợp đồng gốc**.
2. Với hồ sơ chưa có hợp đồng, bấm **Thêm hợp đồng mới**. Nhập số hợp đồng duy nhất, loại hợp đồng, ngày bắt đầu/kết thúc, lương cơ bản, cơ cấu lương và giờ làm/tuần. Kiểm tra phòng ban, chức vụ hiện tại và nội dung điều khoản. Lưu bản nháp.
3. Bấm **Gửi duyệt** rồi dùng tài khoản có quyền **Duyệt**. Sau bước duyệt hồ sơ còn ở **Chờ xử lý**, với nhãn chờ kích hoạt. Bấm **Kích hoạt hợp đồng** khi muốn dùng bản đó để tính kỳ phù hợp.
4. Để tái ký, bấm **Tái ký** trên dòng hợp đồng gốc đang hiệu lực. Kiểm tra loại, parent và các khoản đã sao chép. Nhập số mới, ngày hiệu lực và chỉnh điều khoản nếu cần. Lưu rồi tìm bản mới ở **Chờ xử lý** trong cùng tab.
5. Duyệt và kích hoạt bản tái ký trên bản sao. Đọc cảnh báo đóng bản cũ trước khi xác nhận. Tải lại hồ sơ nếu tab chưa hiển thị mới. Kiểm tra bản cũ ở lịch sử và chỉ còn một bản hiệu lực. Nếu thử thay đổi lương giữa kỳ, ghi lại lỗi bao phủ kỳ.
6. Khi cần chấm dứt, mở hồ sơ hiệu lực và dùng **Đóng hợp đồng**. Xác nhận bản ghi vẫn mở xem được trong lịch sử.

**Đạt khi** · Bản tái ký có đúng hợp đồng gốc, trạng thái và nhóm đồng nhất. Payroll dùng hồ sơ hiệu lực bao phủ kỳ. Bằng chứng chụp nhóm hợp đồng và trường parent, kèm số hợp đồng.

### 4.6. Phụ cấp và lịch sử chính sách · PC-01 đến PC-04

1. Mở hợp đồng nháp và cuộn đến **Phụ cấp** dưới khu vực lương. Bấm **Thêm một dòng**, chọn loại, nhập số tiền tháng, lưu dòng rồi lưu hợp đồng. Bấm lại dòng để mở cửa sổ sửa.
2. Nếu thiếu loại, mở **Cấu hình phụ cấp** từ hợp đồng đã lưu hoặc thiết lập Nhân viên, dùng tài khoản duyệt để tạo loại. Chọn chế độ chịu thuế, miễn hoặc miễn đến giới hạn. Quay lại hợp đồng và chọn loại vừa tạo.
3. Thử ăn trưa `2.000.000` với trần `730.000`, rồi thử xăng xe `3.000.000` với trần `1.000.000`. So phần miễn và chịu thuế trên từng dòng. Khi đối chiếu tổng thu nhập, cộng đủ toàn bộ số phụ cấp.
4. Muốn đổi chính sách trong tương lai, mở loại phụ cấp → **Lịch sử chính sách**, thêm phiên bản với ngày hiệu lực, chế độ, ngưỡng và lý do. Chọn ngày sau các kỳ đã dùng chính sách nếu hệ thống báo chặn.
5. Với hợp đồng đã duyệt, mở hợp đồng gốc và dùng **Tạo phụ lục điều chỉnh phụ cấp** hoặc luồng tái ký thích hợp. Đối chiếu lại mức đóng bảo hiểm nếu nghiệp vụ có thay đổi.

**Đạt khi** · Số tiền và phần miễn/chịu thuế khớp từng dòng. Không đổi hồi tố chính sách đã dùng. Ghi rõ ngưỡng của bộ demo và ngưỡng được nghiệp vụ phê duyệt nếu hai bộ khác nhau.

### 4.7. Tạo kỳ và nhập file công/KPI · IMP-01 đến IMP-05

1. Vào **Tiền lương → Công • Hiệu quả • Lương**. Chọn SMBPlus, năm, tháng. Bấm **Thiết lập kỳ lương** để chọn hoặc tạo kỳ. Kiểm tra khoảng ngày, số công chuẩn, giờ/ngày và các cờ yêu cầu nguồn công, hiệu quả.
2. Từ màn hình tháng bấm **Nhập công Excel** hoặc **Nhập hiệu quả Excel**. Trường hợp cần tạo mapping, vào **Tiền lương → Thiết lập và lịch sử → Nhập liệu và công thức → Mapping file**. Tạo theo đúng công ty và tập dữ liệu, nạp file mẫu, đọc tiêu đề, ánh xạ cột, rồi duyệt mapping.
3. Với công ngang, xác định cột ngày đầu tiên và đủ 31 vị trí ngày. Chọn mapping ký hiệu hoặc giờ. Để trống cột ngày vượt số ngày của tháng. Với KPI, ánh xạ mã nhân viên và khoản KPI. Dùng sheet tháng tương ứng, chỉ chọn dòng Maketting cho kịch bản SMBPlus.
4. Tạo đợt, chọn mapping, kỳ và file. Nếu mapping dùng nhận diện cấp đợt, điền **Phiên bản nguồn** và **Tham chiếu xác nhận**. Bấm xem trước và mở log từng dòng nếu báo lỗi.
5. Ghi đợt sau khi tất cả dòng hợp lệ. Quay về màn hình tháng, bấm **Xem dữ liệu tháng**, đối chiếu một nhân viên và tổng công/KPI. Khi sửa, giữ nguồn và khóa nguồn, tăng revision, ghi rõ lý do rồi xem trước lại.
6. Trên bản sao, thử lần lượt mã nhân viên sai, ngày 31/09, mapping khoản lương từ file KPI và cùng revision với giá trị đã đổi. Mỗi lần dùng file thử riêng để dễ xác định lỗi.

**Đạt khi** · Công và KPI đi đúng kỳ, không nhập đè lương/phụ cấp từ file. Batch lỗi không để lại dòng ghi dở. Lưu mã batch, số dòng và một ví dụ revision trước/sau vào biên bản.

### 4.8. Bảng công, ký hiệu và xem lịch sử · CNG-01 đến CNG-03

1. Mở [Bảng nhập công theo tháng](http://localhost:8069/odoo/action-295). Chọn tháng và công ty. Tìm một dòng IT và đối chiếu **Tăng ca 30**. Cuộn ngang để đọc ký hiệu theo ngày.
2. Để thử nhập tay, dùng kỳ mở và ô trống thuộc nguồn web. Bấm ô trên dòng nhân viên, nhập `X`, `S1` hoặc `X+TC1`. Có thể dán vùng từ Excel. Theo dõi **Giờ thường**, **Tăng ca**, **Tổng giờ**, **Ngày công** rồi bấm **Lưu công**.
3. Để thêm mã, nhập mã chưa có rồi bấm **Thêm mã**, hoặc dùng **Thêm ký hiệu** ở đầu bảng. Nhập giờ thường, giờ tăng ca và lưu bằng tài khoản đủ quyền. Thử chỉnh hoặc bỏ mã; kiểm tra giờ đã ghi trước vẫn đúng.
4. Bấm **Xem log** sau khi lưu. Đổi tháng sang 09 rồi trở về 10 để kiểm tra lịch sử. Với ô công import, dùng chi tiết nguồn hoặc batch để sửa. Nếu tháng đang khóa lương, dùng **Sang bảng lương để mở khóa**.
5. Nếu cần khóa công riêng trước khi tính lương, bấm **Khóa nhập công** ở kỳ mở. Kiểm tra cả lưu ô và import đều bị chặn. Mở khóa riêng từ bảng công khi lương đang mở.

**Đạt khi** · Tổng đổi theo dữ liệu nhập, giờ tăng ca tách đúng, lịch sử tháng không lẫn. Ghi mã nhân viên, ngày thử, mã ký hiệu, giờ trước/sau và log.

### 4.9. Bảng lương, công thức và điều chỉnh · LNG-01, LNG-02

1. Mở [Bảng nhập lương theo tháng](http://localhost:8069/odoo/action-296). Chọn 09/2026 hoặc 10/2026. Dùng tháng demo đã tính để xem, hoặc kỳ mở trên bản sao để thao tác.
2. Đối chiếu ít nhất ba người. Chọn một nhân viên Maketting có KPI, một nhân viên IT có 30 giờ tăng ca và một nhân viên ngoài hai nhóm. So lương theo công, KPI, tăng ca, phụ cấp hợp đồng, bảo hiểm, thuế và thực nhận.
3. Trong kỳ mở, bấm **Tính theo công thức**. Nếu bị chặn, ghi lại đúng lỗi, kiểm tra hợp đồng, dữ liệu công, công chuẩn và cơ cấu lương. Chạy lại sau khi sửa nguyên nhân.
4. Thử ghi đè một ô khoản lương bằng số mới, bấm **Lưu và tính lại**, nhập lý do. Tải lại và kiểm tra số cùng thực nhận. Tiếp theo xóa giá trị nhập tay trong ô, lưu với lý do khác, đối chiếu kết quả trở về tự động.
5. Để thay công thức, mở **Thiết lập và lịch sử → Công thức lương**. Tạo bản nháp hoặc phiên bản mới, chọn khoản và ngày hiệu lực, nhập biểu thức và dữ liệu thử, chạy thử rồi duyệt. Ví dụ quy đổi Excel `=ROUND(G12*U12/N12,0)` cho lương theo công. Thử cả đầu vào thiếu hoặc công chuẩn bằng 0.
6. Kiểm tra **Điều chỉnh lương và lịch sử** để thấy người duyệt, lý do và bản trả về công thức. Báo lỗi nếu kết quả tự động và số nhập tay bị lẫn sau tải lại.

**Đạt khi** · Số đầu vào và số tự động phân biệt rõ. Tổng thực nhận thay đổi sau tính lại và truy được nguồn hợp đồng, công, KPI hoặc bản điều chỉnh.

### 4.10. Khóa, mở khóa, chốt và phiếu lương · LNG-03 đến LNG-05

1. Trên bản sao và đúng tháng, ở bảng lương bấm **Khóa lương**, điền lý do và xác nhận. Mở bảng công cùng kỳ. Thử sửa một ô và thử xem trước file công.
2. Quay lại bảng lương, bấm **Mở khóa lương**. Thử bỏ trống lý do, sau đó nhập lý do hợp lệ. Nếu công còn khóa riêng, mở khóa công sau bước này.
3. Sửa một nguồn đầu vào được phép, lưu và tính lại. Đối chiếu lần tính mới, kết quả cũ trong log và số mới trên bảng.
4. Khi nghiệm thu chốt, mở bảng lương đã tính trong **Thiết lập và lịch sử**. Thực hiện luồng rà soát, duyệt và chốt theo quyền. Mở danh sách **Phiếu lương**, chọn nhân viên và kỳ. So các thành phần với bảng đã chốt.
5. Thử mở lại sau duyệt/chốt và ghi thông báo chặn. Dừng ca thử ở trạng thái đã định trước của bản sao; tránh thao tác chốt trên DB demo đang trình bày.

**Đạt khi** · Khóa lương khóa cùng kỳ công. Lý do mở khóa truy được. Kỳ đã duyệt/chốt không dùng luồng mở lại. Phiếu lương chính thức khớp lần tính đã chốt.

### 4.11. Báo cáo, Excel và log · XLS-01, SEC-01, SEC-02, UAT-01

1. Mở **Tiền lương → Công • Hiệu quả • Lương**, chọn công ty, tháng, năm. Bấm **Xem dữ liệu tháng**. Để xem toàn bộ, bỏ lọc nhân viên. Bấm biểu tượng công/hiệu quả hoặc phiếu lương trên dòng để xem chi tiết.
2. Bấm **Xuất Excel lương** tại màn hình tháng hoặc dùng nút xuất trong **Bảng lương theo mẫu Excel**. Tải file, mở sheet **Luong** và **CongThuc_Log**. Kiểm tra đúng tên kỳ, đủ 52 cột và số dòng theo kết quả đã tính.
3. Chọn một mã nhân viên, so **G** lương hợp đồng, **V** lương theo công, **AF** bảo hiểm NLĐ, **AL** thuế và **AM** thực nhận với giao diện. Dùng sheet log để truy mã khoản và phiên bản công thức. Với phụ cấp theo hợp đồng, kiểm tra cả phần miễn và chịu thuế.
4. Dùng mục **Nhập liệu và công thức → Log dòng** để truy lỗi import và mục log lương/phê duyệt để đối chiếu lần tính, người thao tác, lý do. Với phân công, xem log ngay trong hồ sơ nhân viên.
5. Dùng tài khoản khác công ty để thử mở action, đường dẫn bản ghi và tải tệp. Sau đó kiểm tra lại tháng 09 và 10 với cùng bộ lọc. Ghi kết quả theo ma trận bên dưới.

**Đạt khi** · Web và Excel khớp cùng kỳ, cùng lần tính. Log đủ truy vết. Người dùng chỉ nhìn thấy dữ liệu đúng công ty và đúng quyền.

### 4.12. Mẫu trình bày kết quả cho quản lý

| Hạng mục | Bằng chứng đề nghị | Điều kiện chấp nhận |
|---|---|---|
| Nhân viên và tổ chức | Cây phòng ban, hồ sơ mẫu và log phân công đã che dữ liệu cá nhân | Cơ cấu đúng, lịch sử và người thao tác rõ. |
| Hợp đồng và phụ cấp | Nhóm trạng thái, dòng tái ký có parent, bảng tách miễn/chịu thuế | Một hồ sơ hiệu lực; tách đúng phụ cấp. |
| Công và hiệu quả | Bảng hai tháng, một dòng IT 30 giờ và batch KPI Maketting | Kỳ, nguồn và revision đúng. |
| Lương và xuất Excel | Bảng tháng, phiếu hoặc bản đối chiếu, sheet Luong và CongThuc_Log | Có thể đối chiếu công thức và thực nhận. |
| Phân quyền và khóa | Kết quả thử hai tài khoản, log mở khóa có lý do | Khóa liên động hoạt động; truy cập trái phạm vi bị chặn. |

## 5. Testcase nghiệm thu

| Mã | Điều kiện và thao tác | Kết quả mong đợi |
|---|---|---|
| ENV-01 | Vào web, đăng nhập tài khoản demo. Mở Doanh nghiệp, Nhân viên, Công, Lương | Có đúng SMBPlus. Tháng 09 và 10 chọn được. Số hồ sơ và kết quả khớp mục 1. |
| ORG-01 | Tạo phòng ban cha A, phòng B chọn A trong popup. Mở cây phòng ban | B nằm dưới A. Công ty đi theo phòng cha. |
| ORG-02 | Thử chọn phòng cha công ty khác hoặc tạo vòng A → B → A | Hệ thống từ chối lưu. Cây hiện có giữ nguyên. |
| EMP-01 | Dùng file VP, kiểm tra mapping mã, họ tên, tình trạng, ngày sinh, liên hệ. Xem trước rồi nhập | Preview nêu dòng hợp lệ/lỗi. Hồ sơ mới khớp mã. Cột bỏ trống khi cập nhật giữ dữ liệu cũ theo cấu hình nhập. |
| EMP-02 | Đổi một mã thành trùng hoặc để thiếu tên rồi xem trước | Báo dòng lỗi trước khi ghi. |
| EMP-03 | Tạo hồ sơ web, tải ảnh đại diện, lý lịch PDF và thêm bằng cấp. Thử tệp sai loại hoặc quá 10 MB | Dữ liệu hợp lệ lưu được, tệp sai bị chặn. |
| ASG-01 | Bấm **Phân công** ngay ngoài danh sách. Chọn phòng, chức vụ thuộc phòng và thêm dự án | Popup lưu thành công. Hồ sơ và danh sách hiện đúng bộ phận, vị trí, dự án. |
| ASG-02 | Sửa phân công đã có, bỏ trống lý do rồi lưu. Nhập lý do và lưu lại | Lần đầu bị chặn. Lần sau có log người nhập trước, người sửa, lý do, trước/sau. |
| ASG-03 | Hai người mở cùng hồ sơ. A lưu trước, B lưu bản cũ | B nhận thông báo phân công đã đổi và phải mở lại popup. |
| EMP-04 | Dùng hồ sơ đã nghỉ. Kiểm tra nút phân công. Bấm **Kích hoạt lại** trong chi tiết | Trước kích hoạt nút phân công ẩn và lưu bị chặn. Sau kích hoạt có thể phân công và có lịch sử. |
| HD-01 | Tạo nháp, nhập số hợp đồng, ngày, lương dương và cơ cấu. Gửi, duyệt rồi kích hoạt | Trạng thái và nhóm hiển thị chuyển đúng từng bước. |
| HD-02 | Bấm **Tái ký** từ hợp đồng hiệu lực. Điền số và ngày mới rồi lưu | Bản nháp nằm trong **Hợp đồng → Chờ xử lý**, loại Tái ký, liên kết đúng hợp đồng gốc. |
| HD-03 | Duyệt rồi kích hoạt bản tái ký trên bản sao | Bản mới là hồ sơ hiệu lực duy nhất, bản trước chuyển lịch sử. Bảng lương mới dùng bản mới nếu bao phủ kỳ. |
| HD-04 | Thử tính kỳ mà hợp đồng bắt đầu giữa kỳ hoặc có hồ sơ trùng hiệu lực | Hệ thống báo cần xử lý dữ liệu hoặc tách kỳ. |
| PC-01 | Tạo phụ cấp ăn trưa 2.000.000, trần miễn 730.000. Xem chi tiết | Miễn 730.000, chịu thuế 1.270.000. Tổng thu nhập cộng đủ 2.000.000. |
| PC-02 | Tạo xăng xe 3.000.000, trần 1.000.000. So với nhân viên xăng xe 2.000.000 | Phần chịu thuế lần lượt 2.000.000 và 1.000.000. |
| PC-03 | Sửa dòng phụ cấp nháp bằng popup. Thử sửa trực tiếp sau duyệt | Nháp sửa được. Hồ sơ đã duyệt yêu cầu hồ sơ điều chỉnh phù hợp. |
| PC-04 | Tạo phiên bản chính sách mới có ngày hiệu lực sau kỳ đã tính | Kỳ cũ giữ số đã tính. Kỳ tương lai dùng phiên bản tương ứng. |
| IMP-01 | Import file công có X, S1, C1, X+TC1 và X+TC2H | Giờ thường lần lượt 8, 4, 4, 8, 8. Tăng ca 0, 0, 0, 4, 2. |
| IMP-02 | Nhập file công chứa ngày 31/09 hoặc mã nhân viên sai | Preview báo lỗi và không ghi cả batch có lỗi. |
| IMP-03 | Nhập lại cùng khóa và phiên bản. Sau đó sửa số với revision cao hơn | Bản giống được nhận diện. Bản sửa ghi đè đúng khóa, log giữ dữ liệu trước và sau. |
| IMP-04 | Preview bản sửa rồi ghi thay đổi khác cho cùng khóa, sau đó commit bản preview cũ | Commit phát hiện xung đột, không ghi dở phần còn lại. |
| IMP-05 | Nhập file KPI chỉ Maketting. Thử ánh xạ file hiệu quả vào BASE hoặc phụ cấp | KPI xuất hiện đúng người. Mapping vào lương cơ bản/phụ cấp bị chặn. |
| CNG-01 | Trên kỳ mở, gõ X, S1, X+TC1 ở ba ngày khác nhau | Trước lưu hiển thị 20 giờ thường, 4 giờ tăng ca, tổng 24 giờ. Sau lưu và tải lại số liệu khớp. |
| CNG-02 | Tạo mã từ ô chưa có, lưu rồi dùng mã. Đổi hoặc bỏ mã | Danh mục cập nhật theo công ty. Các ô đã lưu giữ số giờ cũ. |
| CNG-03 | Hai người cùng mở bảng rồi sửa một ô. Hoặc nhập trùng ngày từ nguồn khác | Người lưu sau nhận lỗi revision/nguồn. Dữ liệu cũ không bị cộng trùng. |
| LNG-01 | Tính kỳ đủ dữ liệu. Kiểm tra BASE, phụ cấp, tăng ca, KPI, bảo hiểm và thực nhận | Lương theo công làm tròn, phụ cấp cộng đúng, KPI chỉ có ở người được nhập, thực nhận khớp tổng thu nhập trừ khấu trừ và thuế. |
| LNG-02 | Kỳ mở, nhập tay 0 hoặc giá trị mới cho một khoản, ghi lý do, lưu. Xóa số nhập tay và lưu lần nữa | 0 được giữ là giá trị hợp lệ. Trả ô về công thức sau khi xóa. Hai lần có lịch sử. |
| LNG-03 | Bấm **Khóa lương** và nhập lý do. Thử ghi bảng công hoặc import công | Lương và công cùng khóa. Bảng công hướng về bảng lương để mở kỳ. |
| LNG-04 | Mở khóa lương nhưng bỏ trống lý do. Nhập lý do và thử lại. Sau đó mở công nếu khóa riêng | Lý do bắt buộc. Kỳ chưa duyệt mở lại được. Kết quả cũ lưu log và cần tính lại. |
| LNG-05 | Duyệt/chốt trên bản sao rồi thử mở lại | Bị chặn mở lại. Phiếu chính thức có thể đối chiếu với lần tính đã chốt. |
| XLS-01 | Xuất tháng 09 hoặc 10. So dòng Luong và CongThuc_Log với bảng web | Luong 52 cột A–AZ. Dữ liệu tiền ở dạng số. Cột AL/AM khớp thuế/thực nhận. Có log khoản và phiên bản. |
| SEC-01 | Hai tài khoản có hai công ty. Thử mở danh sách, đổi ID trên URL, gọi nhập/xuất, tải tệp hoặc xem audit của công ty kia | Chỉ thấy dữ liệu đúng phạm vi. URL hoặc thao tác trực tiếp bị chặn. |
| SEC-02 | Tài khoản chỉ nhập liệu thử duyệt mapping, kích hoạt hợp đồng và mở khóa lương | Thao tác yêu cầu quyền duyệt bị từ chối. |
| UAT-01 | Đổi tháng liên tục giữa 09 và 10, đổi ngôn ngữ nếu dùng | Dữ liệu, tháng và công ty đúng sau mỗi lần đổi. Nhãn tùy theo phần dịch đã có. |

## 6. Đối soát số demo và giới hạn

- Ca chuẩn 22 ngày với 21 công thực tế, lương hợp đồng 5.300.000 đ thì lương theo công làm tròn là **5.059.091 đ**. Lịch demo dùng một ngày S1 và một ngày C1, các ngày còn lại theo ký hiệu trong file công.
- IT có 30 giờ tăng ca mỗi tháng. Cấu hình demo tính ngày thường hệ số 150%, dùng 8 giờ chuẩn/ngày. Theo công thức cấu hình, mức tăng ca cho 30 giờ và 22 công chuẩn là **1.355.114 đ**.
- Với mức đóng demo 5.300.000 đ, tổng bảo hiểm người lao động theo cấu hình hiện tại là **556.500 đ**. So cột AF và các cột bảo hiểm người lao động trong Excel, rồi đối chiếu AM với số thực nhận.
- Mẫu lương gốc thiếu công thức trên dòng nhân viên. File đối chiếu có công thức lương theo công. KPI lấy từ file hiệu quả mô phỏng đã điền. Thuế, hệ số tăng ca, giờ Senior và cách xử lý phụ cấp nhà ở/đi lại là cấu hình demo đã chốt để trình diễn. Nghiệm thu công thức doanh nghiệp thực tế cần workbook còn nguyên công thức hoặc bảng quy tắc đã ký duyệt.
- Nếu kỳ đã duyệt/chốt cần sửa sau nghiệm thu, sử dụng quy trình điều chỉnh do nghiệp vụ phê duyệt. Tài liệu bàn giao giữ nguyên dữ liệu thực hiện và ghi riêng các ca cần chạy trên bản sao.

## 7. Biên bản nghiệm thu

| Trường | Nội dung cần ghi |
|---|---|
| Môi trường và bản code | Tên DB, thời điểm, phiên bản/commit hoặc gói bàn giao |
| Người kiểm thử và người duyệt | Tên và vai trò |
| Phạm vi | Mã ca đã chạy và ca còn chờ |
| Sai lệch | Mã ca, kỳ, mã nhân viên, bước tái hiện, kết quả mong đợi/thực tế, log |
| Kết luận | Đạt, đạt có điều kiện hoặc cần sửa, kèm người chịu trách nhiệm |

## Phụ lục A. Chỉ mục model trong mã nguồn

Bảng dưới đây được trích từ định nghĩa Python. Mỗi dòng cho biết nơi khai báo, trường và các điểm xử lý vòng đời. “CRUD ORM” nghĩa là lớp khai báo dùng cơ chế ORM mặc định cho các thao tác chưa override tại đây. Quyền, rule, trạng thái, quan hệ và lớp kế thừa vẫn quyết định hành vi cuối cùng. Phần 3 là quy trình thao tác cho các model trong demo. Addon chưa cài chỉ được liệt kê để người tiếp nhận truy mã.

### hrm_base — đang cài

| Model và loại | Trường khai báo chính | Điểm xử lý vòng đời và nơi khai báo |
|---|---|---|
| `hrm.audit.log` · ORM | `tenant_id`, `actor_user_id`, `actor_employee_ref`, `action`, `entity_type`, `entity_id`, `entity_uuid`, `request_id`, `correlation_id`, `ip_address`, `user_agent`, `old_value` và 2 trường khác | `unlink`, `write`. `addons/hrm_base/models/platform.py` |
| `hrm.base.mixin` · Abstract | `uuid`, `version` | Chỉ đọc hoặc khai báo dùng chung. `write`. `addons/hrm_base/models/mixins.py` |
| `hrm.business.unit` · ORM | `tenant_id`, `company_id`, `parent_id`, `child_ids`, `code`, `name`, `manager_user_id`, `status` | CRUD ORM. `addons/hrm_base/models/organization.py` |
| `hrm.company` · ORM | `tenant_id`, `parent_company_id`, `child_ids`, `res_company_id`, `code`, `name`, `legal_name`, `registration_no`, `country_code`, `currency_code`, `timezone`, `status` | CRUD ORM. `addons/hrm_base/models/organization.py` |
| `hrm.configuration` · ORM | `tenant_id`, `scope_type`, `scope_code`, `config_key`, `config_value`, `effective_from`, `effective_to`, `status` | CRUD ORM. `addons/hrm_base/models/platform.py` |
| `hrm.cost.center` · ORM | `tenant_id`, `company_id`, `parent_id`, `code`, `name`, `status` | CRUD ORM. `addons/hrm_base/models/organization.py` |
| `hrm.department` · ORM | `tenant_id`, `company_id`, `business_unit_id`, `parent_id`, `child_ids`, `code`, `name`, `manager_user_id`, `cost_center_id`, `status`, `effective_from`, `effective_to` | CRUD ORM. `addons/hrm_base/models/organization.py` |
| `hrm.feature.flag` · ORM | `tenant_id`, `key`, `enabled`, `configuration`, `effective_from`, `effective_to` | CRUD ORM. `addons/hrm_base/models/platform.py` |
| `hrm.location` · ORM | `tenant_id`, `company_id`, `parent_id`, `code`, `name`, `location_type`, `address_line1`, `address_line2`, `city`, `state`, `postal_code`, `country_code` và 2 trường khác | CRUD ORM. `addons/hrm_base/models/organization.py` |
| `hrm.permission` · ORM | `code`, `resource`, `action`, `description` | CRUD ORM. `addons/hrm_base/models/rbac.py` |
| `hrm.role` · ORM | `tenant_id`, `code`, `name`, `is_system`, `status`, `permission_ids` | CRUD ORM. `addons/hrm_base/models/rbac.py` |
| `hrm.role.permission` · ORM | `role_id`, `permission_id` | CRUD ORM. `addons/hrm_base/models/rbac.py` |
| `hrm.role.scope` · ORM | `tenant_id`, `role_id`, `scope_type`, `scope_ref`, `configuration` | CRUD ORM. `addons/hrm_base/models/rbac.py` |
| `hrm.tenant` · ORM | `code`, `name`, `slug`, `status`, `timezone`, `locale`, `default_currency`, `country_code`, `settings`, `company_ids` | `_check_currency`. `addons/hrm_base/models/tenant.py` |
| `hrm.user.role` · ORM | `user_id`, `role_id`, `effective_from`, `effective_to` | CRUD ORM. `addons/hrm_base/models/rbac.py` |

### hrm_data_import — đang cài

| Model và loại | Trường khai báo chính | Điểm xử lý vòng đời và nơi khai báo |
|---|---|---|
| `hrm.allowance.type` · ORM | `name`, `code`, `company_id`, `tenant_id`, `tax_mode`, `version_ids`, `active` | `_check_policy`, `create`, `write`. `addons/hrm_data_import/models/allowances.py` |
| `hrm.allowance.version` · ORM | `type_id`, `company_id`, `effective_from`, `tax_mode`, `reason` | `create`, `write`. `addons/hrm_data_import/models/allowances.py` |
| `hrm.attendance.day` · SQL view | `company_id`, `period_id`, `employee_id`, `employee_code`, `year`, `month`, `work_date`, `hours`, `overtime_hours`, `attendance_symbol`, `project_code`, `source` và 3 trường khác | Chỉ đọc hoặc khai báo dùng chung. `init`. `addons/hrm_data_import/models/timesheet_report.py` |
| `hrm.attendance.month` · SQL view | `company_id`, `tenant_id`, `period_id`, `period_start`, `period_label`, `year`, `month`, `employee_id`, `employee_code`, `assignment_department`, `assignment_projects`, `employment_status` và 7 trường khác | Chỉ đọc hoặc khai báo dùng chung. `action_details`, `action_monthly_workspace`, `init`. `addons/hrm_data_import/models/timesheet_report.py` |
| `hrm.attendance.symbol` · ORM | `company_id`, `code`, `regular_hours`, `overtime_hours`, `enabled` | `_check_symbol`, `create`, `write`. `addons/hrm_data_import/models/attendance_grid.py` |
| `hrm.company.entry.defaults` · Abstract | Theo model gốc hoặc khai báo động | Chỉ đọc hoặc khai báo dùng chung. . `addons/hrm_data_import/models/quick_entry.py` |
| `hrm.contract.allowance` · ORM | `contract_id`, `company_id`, `type_id`, `tax_mode`, `exempt_limit`, `tax_exempt_amount`, `taxable_amount` | `_check_editable`, `_check_line`, `create`, `unlink`, `write`. `addons/hrm_data_import/models/allowances.py` |
| `hrm.demo.source` · ORM | `workspace_id`, `company_id`, `tenant_id`, `filename`, `file_data`, `sha256`, `sheets`, `record_count`, `state`, `details`, `profile_id` | `action_download`, `unlink`, `write`. `addons/hrm_data_import/models/demo_workspace.py` |
| `hrm.demo.workspace` · ORM | `name`, `company_id`, `tenant_id`, `prepared_on`, `source_ids`, `employee_count`, `working_count`, `departed_count`, `notes` | `action_employees`, `action_logs`, `action_profiles`. `addons/hrm_data_import/models/demo_workspace.py` |
| `hrm.employee.assignment.log` · ORM | `employee_id`, `company_id`, `assignment_id`, `actor_id`, `previous_actor_id`, `reason`, `before`, `after` | CRUD ORM. `addons/hrm_data_import/models/employee_assignment.py` |
| `hrm.employee.assignment.wizard` · Tạm | `employee_id`, `company_id`, `assignment_id`, `assignment_stamp`, `department_id`, `position_id`, `new_position`, `position_title`, `project_ids`, `reason` | `action_apply`. `addons/hrm_data_import/models/employee_assignment.py` |
| `hrm.employee.import` · ORM | `company_id`, `tenant_id`, `filename`, `file_data`, `sheet`, `result`, `state`, `update_existing`, `mapping_ids`, `mapping`, `preview` | `action_import`, `action_preview`, `create`, `unlink`, `write`. `addons/hrm_data_import/models/hr_workspace.py` |
| `hrm.employee.import.column` · ORM | `import_id`, `company_id`, `source`, `target` | `create`, `unlink`, `write`. `addons/hrm_data_import/models/hr_workspace.py` |
| `hrm.employee.project` · ORM | `name`, `company_id`, `active` | CRUD ORM. `addons/hrm_data_import/models/employee_assignment.py` |
| `hrm.import.batch` · ORM | `profile_id`, `company_id`, `tenant_id`, `period_id`, `filename`, `file_data`, `file_hash`, `source_revision`, `approval_reference`, `state`, `message`, `line_ids` và 2 trường khác | `action_commit`, `action_preview`, `create`, `unlink`, `write`. `addons/hrm_data_import/models/imports.py` |
| `hrm.import.input` · ORM | `tenant_id`, `company_id`, `period_id`, `dataset`, `source`, `source_record_id`, `revision`, `employee_id`, `payload`, `batch_id` | CRUD ORM. `addons/hrm_data_import/models/imports.py` |
| `hrm.import.line` · ORM | `batch_id`, `tenant_id`, `row_no`, `raw`, `normalized`, `previous`, `result`, `error` | CRUD ORM. `addons/hrm_data_import/models/imports.py` |
| `hrm.import.mapping` · ORM | `profile_id`, `tenant_id`, `column`, `target`, `data_type`, `required`, `date_format`, `source_header`, `component_id` | `create`, `unlink`, `write`. `addons/hrm_data_import/models/imports.py` |
| `hrm.import.profile` · ORM | `name`, `tenant_id`, `company_id`, `dataset`, `source`, `revision`, `sheet`, `header_row`, `data_start_row`, `cached_header`, `batch_identity`, `locale` và 12 trường khác | `action_add_amount_columns`, `action_approve`, `action_download_template`, `action_read_headers`, `create`, `unlink`, `write`. `addons/hrm_data_import/models/imports.py` |
| `hrm.manual.input` · ORM | `company_id`, `tenant_id`, `period_id`, `employee_id`, `dataset`, `work_date`, `regular_hours`, `component_id`, `amount`, `source_record_id`, `revision`, `approval_reference` và 1 trường khác | `action_publish`, `create`, `write`. `addons/hrm_data_import/models/business_flow.py` |
| `hrm.monthly.line` · ORM | `workspace_id`, `company_id`, `employee_id`, `employee_code`, `period_id`, `hours`, `paid_days`, `performance`, `base_salary`, `attendance_count`, `performance_count`, `result_id` và 4 trường khác | `action_inputs`, `action_salary`. `addons/hrm_data_import/models/monthly_workspace.py` |
| `hrm.monthly.workspace` · ORM | `name`, `company_id`, `year`, `month`, `employee_id`, `period_id`, `line_ids`, `notice` | `_check_scope`, `action_all_employees`, `action_calculate`, `action_import_attendance`, `action_import_performance`, `action_manual`, `action_period`, `action_refresh`, `action_timesheet`, `write`. `addons/hrm_data_import/models/monthly_workspace.py` |
| `hrm.payroll.formula` · ORM | `tenant_id`, `component_id`, `effective_from`, `effective_to`, `expression`, `test_context`, `test_result`, `state`, `approved_by` | `action_approve`, `action_test`, `create`, `unlink`, `write`. `addons/hrm_data_import/models/formulas.py` |
| `hrm.quick.organization.entry` · Abstract | Theo model gốc hoặc khai báo động | Chỉ đọc hoặc khai báo dùng chung. `_check_organization_parent`, `create`, `write`. `addons/hrm_data_import/models/quick_entry.py` |
| `hrm.salary.adjustment` · ORM | `company_id`, `tenant_id`, `period_id`, `employee_id`, `component_id`, `amount`, `restore_formula`, `reason`, `state`, `approved_by`, `approved_at` | `action_approve`, `create`, `unlink`, `write`. `addons/hrm_data_import/models/salary_quick.py` |

### hrm_employee — đang cài

| Model và loại | Trường khai báo chính | Điểm xử lý vòng đời và nơi khai báo |
|---|---|---|
| `hrm.contract.type` · ORM | `tenant_id`, `code`, `name`, `employment_category`, `default_duration_days`, `is_indefinite`, `status` | CRUD ORM. `addons/hrm_employee/models/employment.py` |
| `hrm.emergency.contact` · ORM | `tenant_id`, `employee_id`, `name`, `relationship`, `phone`, `email`, `address`, `priority`, `is_primary` | CRUD ORM. `addons/hrm_employee/models/employee_related.py` |
| `hrm.employee.assignment` · ORM | `tenant_id`, `employee_id`, `company_id`, `business_unit_id`, `department_id`, `position_id`, `job_id`, `grade_id`, `location_id`, `manager_employee_id`, `assignment_type`, `is_primary` và 4 trường khác | `_check_no_overlap_primary`, `unlink`. `addons/hrm_employee/models/employment.py` |
| `hrm.employee.certification` · ORM | `tenant_id`, `employee_id`, `certification_name`, `issuer`, `certificate_no`, `issued_date`, `expiry_date`, `status`, `document_id` | CRUD ORM. `addons/hrm_employee/models/employee_related.py` |
| `hrm.employee.contact` · ORM | `tenant_id`, `employee_id`, `contact_type`, `label`, `value`, `is_primary`, `effective_from`, `effective_to` | CRUD ORM. `addons/hrm_employee/models/employee_related.py` |
| `hrm.employee.contract` · ORM | `tenant_id`, `employee_id`, `company_id`, `contract_type_id`, `contract_no`, `start_date`, `end_date`, `probation_start`, `probation_end`, `currency_code`, `status`, `signed_at` và 1 trường khác | `_move`, `action_activate`, `action_approve`, `action_expire`, `action_submit`, `unlink`. `addons/hrm_employee/models/employment.py` |
| `hrm.employee.document` · ORM | `tenant_id`, `employee_id`, `document_type`, `file_name`, `storage_key`, `mime_type`, `file_size_bytes`, `checksum_sha256`, `issued_at`, `expires_at`, `status` | CRUD ORM. `addons/hrm_employee/models/employee_related.py` |
| `hrm.employee.education` · ORM | `tenant_id`, `employee_id`, `institution`, `degree`, `field_of_study`, `start_date`, `end_date`, `grade`, `country_code`, `document_id` | CRUD ORM. `addons/hrm_employee/models/employee_related.py` |
| `hrm.employee.family` · ORM | `tenant_id`, `employee_id`, `person_id`, `name`, `relationship_type`, `is_dependent`, `date_of_birth`, `notes` | CRUD ORM. `addons/hrm_employee/models/employee_related.py` |
| `hrm.employee.history` · ORM | `tenant_id`, `employee_id`, `event_type`, `event_at`, `actor_id`, `reference_type`, `reference_id`, `payload` | `unlink`, `write`. `addons/hrm_employee/models/employee_related.py` |
| `hrm.employee.skill` · ORM | `tenant_id`, `employee_id`, `name`, `level`, `verified_at` | CRUD ORM. `addons/hrm_employee/models/employee_related.py` |
| `hrm.employment.status.history` · ORM | `tenant_id`, `employee_id`, `from_status`, `to_status`, `effective_at`, `reason`, `actor_id`, `reference_type`, `reference_id` | `unlink`, `write`. `addons/hrm_employee/models/employment.py` |
| `hrm.grade` · ORM | `tenant_id`, `company_id`, `code`, `name`, `level`, `currency_code`, `status` | CRUD ORM. `addons/hrm_employee/models/catalog.py` |
| `hrm.job` · ORM | `tenant_id`, `company_id`, `hr_job_id`, `code`, `title`, `description`, `grade_id`, `status` | CRUD ORM. `addons/hrm_employee/models/catalog.py` |
| `hrm.person` · ORM | `tenant_id`, `person_code`, `first_name`, `middle_name`, `last_name`, `display_name`, `preferred_name`, `date_of_birth`, `gender`, `nationality_code`, `marital_status`, `photo` và 2 trường khác | CRUD ORM. `addons/hrm_employee/models/person.py` |
| `hrm.position` · ORM | `tenant_id`, `company_id`, `department_id`, `job_id`, `grade_id`, `location_id`, `code`, `title`, `headcount_limit`, `status`, `effective_from`, `effective_to` | CRUD ORM. `addons/hrm_employee/models/catalog.py` |
| `hrm.probation` · ORM | `tenant_id`, `employee_id`, `contract_id`, `start_date`, `planned_end_date`, `actual_end_date`, `result`, `status`, `notes` | `_move`, `action_extend`, `action_fail`, `action_pass`, `action_start`, `unlink`. `addons/hrm_employee/models/employment_event.py` |
| `hrm.promotion` · ORM | `tenant_id`, `employee_id`, `from_assignment_id`, `to_position_id`, `from_grade_id`, `to_grade_id`, `effective_date`, `reason`, `status`, `workflow_instance_id` | `action_approve`, `action_done`, `unlink`. `addons/hrm_employee/models/employment_event.py` |
| `hrm.reporting.line` · ORM | `tenant_id`, `company_id`, `manager_employee_id`, `employee_id`, `relationship_type`, `effective_from`, `effective_to` | CRUD ORM. `addons/hrm_employee/models/catalog.py` |
| `hrm.salary.history` · ORM | `tenant_id`, `employee_id`, `contract_id`, `effective_from`, `effective_to`, `currency_code`, `change_type`, `change_reason`, `source_type`, `source_id` | `unlink`, `write`. `addons/hrm_employee/models/employment.py` |
| `hrm.transfer` · ORM | `tenant_id`, `employee_id`, `from_company_id`, `to_company_id`, `from_department_id`, `to_department_id`, `from_position_id`, `to_position_id`, `effective_date`, `reason`, `status`, `workflow_instance_id` | `action_approve`, `action_done`, `unlink`. `addons/hrm_employee/models/employment_event.py` |

### hrm_payroll — đang cài

| Model và loại | Trường khai báo chính | Điểm xử lý vòng đời và nơi khai báo |
|---|---|---|
| `hrm.bonus` · ORM | `tenant_id`, `employee_id`, `bonus_type`, `currency_code`, `effective_date`, `reason`, `status`, `workflow_instance_id` | `action_approve`, `action_reject`, `write`. `addons/hrm_payroll/models/run.py` |
| `hrm.deduction` · ORM | `tenant_id`, `employee_id`, `deduction_type`, `currency_code`, `effective_from`, `effective_to`, `reason`, `status`, `workflow_instance_id` | `action_activate`, `action_close`. `addons/hrm_payroll/models/run.py` |
| `hrm.employee.salary` · ORM | `tenant_id`, `employee_id`, `structure_id`, `effective_from`, `effective_to`, `currency_code`, `configuration`, `status` | `_check_no_overlap`. `addons/hrm_payroll/models/salary.py` |
| `hrm.payroll` · ORM | `tenant_id`, `company_id`, `period_id`, `run_no`, `calculation_version`, `started_at`, `completed_at`, `status`, `item_ids` | `action_approve`, `action_calculate`, `action_finalize`, `action_mark_paid`, `action_review`, `action_start`, `unlink`, `write`. `addons/hrm_payroll/models/run.py` |
| `hrm.payroll.item` · ORM | `tenant_id`, `payroll_id`, `employee_id`, `currency_code`, `status` | `unlink`, `write`. `addons/hrm_payroll/models/run.py` |
| `hrm.payroll.period` · ORM | `tenant_id`, `company_id`, `period_code`, `period_start`, `period_end`, `payment_date`, `status`, `payroll_ids` | `_check_dates`, `_move`, `action_approve`, `action_finalize`, `action_mark_calculated`, `action_mark_paid`, `action_start_processing`, `action_to_review`, `unlink`. `addons/hrm_payroll/models/run.py` |
| `hrm.payslip` · ORM | `tenant_id`, `payroll_id`, `employee_id`, `payslip_no`, `currency_code`, `issued_at`, `status`, `document_id`, `item_ids` | `unlink`, `write`. `addons/hrm_payroll/models/run.py` |
| `hrm.payslip.item` · ORM | `tenant_id`, `payslip_id`, `payroll_id`, `employee_id`, `salary_component_id`, `code`, `name`, `currency_code`, `sequence_no`, `status` | `unlink`, `write`. `addons/hrm_payroll/models/run.py` |
| `hrm.salary.component` · ORM | `tenant_id`, `structure_id`, `code`, `name`, `component_type`, `calculation_type`, `sequence_no`, `configuration`, `status` | CRUD ORM. `addons/hrm_payroll/models/salary.py` |
| `hrm.salary.structure` · ORM | `tenant_id`, `company_id`, `code`, `name`, `currency_code`, `effective_from`, `effective_to`, `status`, `component_ids` | CRUD ORM. `addons/hrm_payroll/models/salary.py` |

### hrm_time — đang cài

| Model và loại | Trường khai báo chính | Điểm xử lý vòng đời và nơi khai báo |
|---|---|---|
| `hrm.attendance` · ORM | `tenant_id`, `employee_id`, `work_date`, `check_in_at`, `check_out_at`, `worked_minutes`, `late_minutes`, `early_leave_minutes`, `overtime_minutes`, `status`, `source`, `calculation_version` và 1 trường khác | `action_lock`, `action_process`, `action_validate`, `unlink`, `write`. `addons/hrm_time/models/attendance.py` |
| `hrm.attendance.adjustment` · ORM | `tenant_id`, `attendance_id`, `employee_id`, `requested_by_id`, `reason`, `old_value`, `new_value`, `status`, `approved_by_id`, `approved_at` | `action_approve`, `action_reject`. `addons/hrm_time/models/attendance.py` |
| `hrm.attendance.device` · ORM | `tenant_id`, `company_id`, `location_id`, `code`, `name`, `device_type`, `external_device_id`, `ip_address`, `status`, `last_sync_at`, `configuration` | CRUD ORM. `addons/hrm_time/models/schedule.py` |
| `hrm.attendance.device.event` · ORM | `tenant_id`, `device_id`, `employee_external_ref`, `employee_id`, `event_type`, `event_time`, `payload`, `external_event_id`, `received_at`, `processed_at` | `unlink`, `write`. `addons/hrm_time/models/attendance.py` |
| `hrm.overtime.request` · ORM | `tenant_id`, `employee_id`, `work_date`, `start_at`, `end_at`, `requested_minutes`, `approved_minutes`, `reason`, `status`, `workflow_instance_id` | `_check_times`, `action_approve`, `action_reject`, `action_submit`. `addons/hrm_time/models/attendance.py` |
| `hrm.shift` · ORM | `tenant_id`, `company_id`, `work_schedule_id`, `code`, `name`, `start_time`, `end_time`, `cross_midnight`, `break_rules`, `status` | `_check_hhmmss`. `addons/hrm_time/models/schedule.py` |
| `hrm.shift.assignment` · ORM | `tenant_id`, `employee_id`, `shift_id`, `effective_from`, `effective_to` | `_check_no_overlap`. `addons/hrm_time/models/schedule.py` |
| `hrm.timesheet` · ORM | `tenant_id`, `employee_id`, `period_start`, `period_end`, `total_minutes`, `status`, `submitted_at`, `approved_at` | `action_approve`, `action_rollup`, `action_submit`. `addons/hrm_time/models/attendance.py` |
| `hrm.work.entry` · ORM | `tenant_id`, `employee_id`, `work_date`, `entry_type`, `unit`, `source_type`, `source_id`, `status` | `unlink`, `write`. `addons/hrm_time/models/attendance.py` |
| `hrm.work.schedule` · ORM | `tenant_id`, `company_id`, `code`, `name`, `timezone`, `rules`, `status` | CRUD ORM. `addons/hrm_time/models/schedule.py` |

### hrm_workflow — đang cài

| Model và loại | Trường khai báo chính | Điểm xử lý vòng đời và nơi khai báo |
|---|---|---|
| `hrm.approval.request` · ORM | `tenant_id`, `instance_id`, `step_id`, `approver_user_id`, `approver_employee_id`, `decision`, `status`, `comment`, `decided_at` | `action_approve`, `action_reject`, `create`, `unlink`, `write`. `addons/hrm_workflow/models/approval.py` |
| `hrm.notification` · ORM | `tenant_id`, `recipient_user_id`, `channel`, `template_code`, `subject`, `payload`, `status`, `scheduled_at`, `sent_at`, `read_at` | `action_mark_read`, `action_mark_sent`, `unlink`. `addons/hrm_workflow/models/notification.py` |
| `hrm.workflow.definition` · ORM | `tenant_id`, `code`, `name`, `entity_type`, `version`, `status`, `configuration`, `step_ids` | `action_activate`, `action_archive`, `unlink`. `addons/hrm_workflow/models/workflow.py` |
| `hrm.workflow.instance` · ORM | `tenant_id`, `definition_id`, `entity_type`, `entity_id`, `entity_uuid`, `current_state`, `started_at`, `started_by_id`, `completed_at`, `status`, `approval_ids` | `action_cancel`, `write`. `addons/hrm_workflow/models/workflow.py` |
| `hrm.workflow.step` · ORM | `tenant_id`, `definition_id`, `step_code`, `name`, `sequence_no`, `approver_type`, `approver_user_id`, `approver_employee_id`, `approver_role_id`, `configuration` | CRUD ORM. `addons/hrm_workflow/models/workflow.py` |

### hrm_integration — có mã nguồn, chưa cài trong demo

| Model và loại | Trường khai báo chính | Điểm xử lý vòng đời và nơi khai báo |
|---|---|---|
| `hrm.api.token` · ORM | `tenant_id`, `name`, `token_hash`, `token_tail`, `expires_at`, `active`, `rate_limit_per_hour`, `window_start`, `requests_in_window`, `last_used_at`, `revoked_at` | `action_generate_new_key`, `action_revoke`, `cron_cleanup_expired`. `addons/hrm_integration/models/api_token.py` |
| `hrm.api.token.show` · Tạm | `name`, `raw`, `expires_at` | CRUD ORM. `addons/hrm_integration/models/api_token.py` |
| `hrm.event.outbox` · ORM | `tenant_id`, `event_id`, `event_type`, `event_version`, `aggregate_type`, `aggregate_id`, `correlation_id`, `payload`, `occurred_at`, `published_at`, `status`, `retry_count` và 1 trường khác | `action_publish_pending`, `unlink`, `write`. `addons/hrm_integration/models/events.py` |
| `hrm.idempotency.key` · ORM | `tenant_id`, `key`, `request_hash`, `response_status`, `response_body`, `created_at`, `expires_at` | CRUD ORM. `addons/hrm_integration/models/events.py` |
| `hrm.import.job` · ORM | `tenant_id`, `entity_type`, `file_storage_key`, `mapping`, `total_rows`, `processed_rows`, `success_rows`, `failed_rows`, `status`, `error_report_storage_key`, `started_at`, `completed_at` | `action_add_result`, `action_fail`, `action_finish`, `action_start`. `addons/hrm_integration/models/integration.py` |
| `hrm.integration.connection` · ORM | `tenant_id`, `provider`, `connection_type`, `external_account_id`, `configuration`, `credential_reference`, `status` | `action_connect`, `action_suspend`. `addons/hrm_integration/models/integration.py` |
| `hrm.webhook.delivery` · ORM | `tenant_id`, `endpoint_id`, `event_id`, `attempt_no`, `status`, `http_status`, `response_body`, `sent_at`, `next_retry_at` | CRUD ORM. `addons/hrm_integration/models/events.py` |
| `hrm.webhook.endpoint` · ORM | `tenant_id`, `name`, `url`, `secret_reference`, `configuration`, `event_filters`, `status`, `delivery_ids` | `_check_secret`. `addons/hrm_integration/models/events.py` |

### hrm_learning — có mã nguồn, chưa cài trong demo

| Model và loại | Trường khai báo chính | Điểm xử lý vòng đời và nơi khai báo |
|---|---|---|
| `hrm.certification` · ORM | `tenant_id`, `employee_id`, `name`, `issuer`, `certificate_no`, `issued_at`, `expires_at`, `status`, `document_id` | CRUD ORM. `addons/hrm_learning/models/learning.py` |
| `hrm.course` · ORM | `tenant_id`, `code`, `name`, `description`, `duration_minutes`, `provider`, `status` | CRUD ORM. `addons/hrm_learning/models/learning.py` |
| `hrm.skill` · ORM | `tenant_id`, `code`, `name`, `category`, `status` | CRUD ORM. `addons/hrm_learning/models/learning.py` |
| `hrm.skill.matrix` · ORM | `tenant_id`, `job_id`, `skill_id`, `required_level`, `effective_from`, `effective_to` | `_check_global_unique_and_overlap`. `addons/hrm_learning/models/learning.py` |
| `hrm.training` · ORM | `tenant_id`, `course_id`, `trainer_employee_id`, `location_id`, `start_at`, `end_at`, `capacity`, `status`, `enrollment_ids` | `action_cancel`, `action_done`, `action_open`. `addons/hrm_learning/models/learning.py` |
| `hrm.training.enrollment` · ORM | `tenant_id`, `training_id`, `employee_id`, `enrolled_at`, `completion_at`, `status` | `action_cancel`, `action_complete`. `addons/hrm_learning/models/learning.py` |
| `hrm.training.plan` · ORM | `tenant_id`, `employee_id`, `name`, `period_start`, `period_end`, `status` | CRUD ORM. `addons/hrm_learning/models/learning.py` |

### hrm_leave — có mã nguồn, chưa cài trong demo

| Model và loại | Trường khai báo chính | Điểm xử lý vòng đời và nơi khai báo |
|---|---|---|
| `hrm.leave.allocation` · ORM | `tenant_id`, `employee_id`, `leave_type_id`, `period_start`, `period_end`, `source_type`, `source_id`, `status` | `action_activate`, `action_cancel`. `addons/hrm_leave/models/leave.py` |
| `hrm.leave.approval` · ORM | `tenant_id`, `request_id`, `approver_employee_id`, `sequence_no`, `decision`, `comment`, `decided_at` | `unlink`, `write`. `addons/hrm_leave/models/leave.py` |
| `hrm.leave.balance.ledger` · ORM | `tenant_id`, `employee_id`, `leave_type_id`, `transaction_type`, `reference_type`, `reference_id`, `occurred_at`, `created_by_id` | `unlink`, `write`. `addons/hrm_leave/models/leave.py` |
| `hrm.leave.policy` · ORM | `tenant_id`, `company_id`, `code`, `name`, `country_code`, `effective_from`, `effective_to`, `status`, `rule_ids` | CRUD ORM. `addons/hrm_leave/models/leave.py` |
| `hrm.leave.policy.rule` · ORM | `tenant_id`, `policy_id`, `leave_type_id`, `rule_type`, `configuration`, `effective_from`, `effective_to` | CRUD ORM. `addons/hrm_leave/models/leave.py` |
| `hrm.leave.request` · ORM | `tenant_id`, `employee_id`, `leave_type_id`, `start_at`, `end_at`, `reason`, `attachment_id`, `status`, `workflow_instance_id`, `approval_ids` | `_check_dates`, `action_approve`, `action_cancel`, `action_reject`, `action_submit`, `action_take`. `addons/hrm_leave/models/leave.py` |
| `hrm.leave.type` · ORM | `tenant_id`, `code`, `name`, `paid`, `requires_attachment`, `allow_negative_balance`, `unit`, `status` | CRUD ORM. `addons/hrm_leave/models/leave.py` |

### hrm_performance — có mã nguồn, chưa cài trong demo

| Model và loại | Trường khai báo chính | Điểm xử lý vòng đời và nơi khai báo |
|---|---|---|
| `hrm.appraisal` · ORM | `tenant_id`, `employee_id`, `cycle_id`, `reviewer_employee_id`, `status`, `comments`, `feedback_ids`, `workflow_instance_id` | `action_calibrate`, `action_finalize`, `action_submit`. `addons/hrm_performance/models/performance.py` |
| `hrm.competency` · ORM | `tenant_id`, `code`, `name`, `description`, `category`, `status` | CRUD ORM. `addons/hrm_performance/models/performance.py` |
| `hrm.feedback.360` · ORM | `tenant_id`, `appraisal_id`, `reviewer_employee_id`, `relationship_type`, `comments`, `submitted_at`, `status` | `action_submit`. `addons/hrm_performance/models/performance.py` |
| `hrm.goal` · ORM | `tenant_id`, `employee_id`, `cycle_id`, `parent_goal_id`, `child_ids`, `title`, `description`, `status` | `action_activate`, `action_done`. `addons/hrm_performance/models/performance.py` |
| `hrm.kpi` · ORM | `tenant_id`, `cycle_id`, `code`, `name`, `measurement_unit`, `target_type`, `configuration` | CRUD ORM. `addons/hrm_performance/models/performance.py` |
| `hrm.okr` · ORM | `tenant_id`, `cycle_id`, `employee_id`, `objective`, `status` | `_check_progress`. `addons/hrm_performance/models/performance.py` |
| `hrm.performance.cycle` · ORM | `tenant_id`, `company_id`, `name`, `period_start`, `period_end`, `status`, `configuration` | `_move`, `action_calibrate`, `action_close`, `action_finalize`, `action_open`, `action_review`. `addons/hrm_performance/models/performance.py` |

### hrm_recruitment — có mã nguồn, chưa cài trong demo

| Model và loại | Trường khai báo chính | Điểm xử lý vòng đời và nơi khai báo |
|---|---|---|
| `hrm.application` · ORM | `tenant_id`, `candidate_id`, `requisition_id`, `current_stage_id`, `applied_at`, `source`, `status`, `rejection_reason`, `interview_ids`, `offer_ids` | `_move`, `action_move_stage`, `action_reject`, `action_withdraw`. `addons/hrm_recruitment/models/application.py` |
| `hrm.candidate` · ORM | `tenant_id`, `person_id`, `candidate_code`, `first_name`, `last_name`, `email`, `phone`, `source`, `status`, `resume_attachment_id`, `application_ids` | CRUD ORM. `addons/hrm_recruitment/models/candidate.py` |
| `hrm.interview` · ORM | `tenant_id`, `application_id`, `interviewer_employee_id`, `scheduled_at`, `duration_minutes`, `location`, `meeting_url`, `status`, `evaluation_ids` | `action_cancel`, `action_done`. `addons/hrm_recruitment/models/application.py` |
| `hrm.interview.evaluation` · ORM | `tenant_id`, `interview_id`, `evaluator_employee_id`, `recommendation`, `comments`, `submitted_at` | `action_submit`. `addons/hrm_recruitment/models/application.py` |
| `hrm.job.requisition` · ORM | `tenant_id`, `company_id`, `department_id`, `position_id`, `job_id`, `requested_by_id`, `approved_headcount`, `target_hire_date`, `description`, `status`, `workflow_instance_id`, `application_ids` | `_move`, `action_approve`, `action_cancel`, `action_fill`, `action_open`, `action_submit`. `addons/hrm_recruitment/models/requisition.py` |
| `hrm.offer` · ORM | `tenant_id`, `application_id`, `employee_id`, `offer_no`, `issued_at`, `expires_at`, `currency_code`, `start_date`, `status`, `document_id`, `workflow_instance_id` | `_move`, `action_accept`, `action_decline`, `action_expire`, `action_send`, `action_submit`. `addons/hrm_recruitment/models/application.py` |
| `hrm.recruitment.stage` · ORM | `tenant_id`, `pipeline_code`, `code`, `name`, `sequence_no`, `stage_type`, `is_terminal`, `status` | CRUD ORM. `addons/hrm_recruitment/models/candidate.py` |

### hrm_vn — có mã nguồn, chưa cài trong demo

| Model và loại | Trường khai báo chính | Điểm xử lý vòng đời và nơi khai báo |
|---|---|---|
| `hrm.insurance.rule` · ORM | `tenant_id`, `code`, `name`, `effective_from`, `effective_to`, `status` | CRUD ORM. `addons/hrm_vn/models/vn_rules.py` |
| `hrm.payroll.rule` · ORM | `tenant_id`, `code`, `name`, `rounding`, `effective_from`, `effective_to`, `status` | CRUD ORM. `addons/hrm_vn/models/vn_rules.py` |
| `hrm.person.identifier` · ORM | `tenant_id`, `person_id`, `id_type`, `id_value_ref`, `issued_at`, `expires_at`, `status` | CRUD ORM. `addons/hrm_vn/models/vn_rules.py` |
| `hrm.statutory.rule` · ORM | `tenant_id`, `code`, `name`, `rule_type`, `configuration`, `effective_from`, `effective_to`, `status` | CRUD ORM. `addons/hrm_vn/models/vn_rules.py` |
| `hrm.tax.rule` · ORM | `tenant_id`, `code`, `name`, `brackets`, `effective_from`, `effective_to`, `status` | CRUD ORM. `addons/hrm_vn/models/vn_rules.py` |

### Model tích hợp của Odoo

| Model | Vị trí các lớp mở rộng |
|---|---|
| `hr.employee` | `addons/hrm_data_import/models/company_scope.py`, `addons/hrm_data_import/models/employee_assignment.py`, `addons/hrm_data_import/models/employee_entry.py`, `addons/hrm_data_import/models/hr_workspace.py`, `addons/hrm_data_import/models/quick_entry.py` |
| `hr.employee.public` | `addons/hrm_data_import/models/company_scope.py` |
| `res.users` | `addons/hrm_base/models/res_users.py`, `addons/hrm_data_import/models/company_scope.py` |
| `ir.access` | `addons/hrm_data_import/models/company_scope.py` |

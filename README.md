# SMBPlus HRM

**Demo quản lý nhân sự, chấm công và tính lương trên Odoo 20.** Theo dõi cùng một nhân viên từ phòng ban, chức vụ và hợp đồng đến bảng công, bảng lương và lịch sử điều chỉnh.

[Mở Odoo](http://localhost:8069) · [Bảng công tháng](http://localhost:8069/odoo/action-295) · [Bảng lương tháng](http://localhost:8069/odoo/action-296) · [Hướng dẫn sử dụng và nghiệm thu](docs/01_VONG_DOI_DU_LIEU_VA_TESTCASE.md) · [Bàn giao kỹ thuật](docs/02_HUONG_DAN_DEV.md)

## Bộ demo

| 26 hồ sơ VP | 2 kỳ đã tính | 42 kết quả lương | 8 nhân viên IT |
|---|---|---|---|
| 21 đang làm, 5 đã nghỉ | Tháng 09 và 10/2026 | 21 kết quả mỗi kỳ | 30 giờ tăng ca/người/kỳ |

SMBPlus có cây phòng ban IT với IT dev và IT helpdesk, cùng Maketting, CSKH và Kế toán. Hồ sơ có vị trí Lead, Senior hoặc Nhân viên. Bảng lương lấy lương cơ bản và phụ cấp từ hợp đồng đang hiệu lực, lấy công và KPI từ đầu vào kỳ, rồi áp dụng công thức, bảo hiểm, thuế và điều chỉnh đã duyệt.

Dữ liệu chấm công, KPI và lương trong ảnh phục vụ demo. Các quy tắc giả định và phần đối chiếu được với Excel có trong [tài liệu nghiệm thu](docs/01_VONG_DOI_DU_LIEU_VA_TESTCASE.md).

## Trình diễn theo luồng nghiệp vụ

### 1. Doanh nghiệp và nhân viên

Bắt đầu ở doanh nghiệp, mở cây phòng ban rồi chọn một nhân viên. Từ danh sách có thể phân công nhanh phòng ban, chức vụ và dự án. Chi tiết nhân viên có tab riêng để theo dõi lịch sử thay đổi.

![Danh sách nhân viên SMBPlus với phòng ban, chức vụ và dự án](assets/readme/03-nhan-vien.jpg)

<details>
<summary>Xem doanh nghiệp, phòng ban, hồ sơ và popup phân công</summary>

**Thông tin doanh nghiệp**

![Thông tin doanh nghiệp SMBPlus](assets/readme/01-doanh-nghiep.jpg)

**Danh sách phòng ban**

![Danh sách phòng ban SMBPlus](assets/readme/02-phong-ban.jpg)

**Hồ sơ và lịch sử phân công**

![Phân công hiện tại và khu vực lịch sử trong hồ sơ](assets/readme/04-ho-so-phan-cong.jpg)

**Popup phân công**

![Popup chọn phòng ban, chức vụ, dự án và lý do điều chỉnh](assets/readme/05-popup-phan-cong.jpg)

</details>

### 2. Hợp đồng, tái ký và phụ cấp

Tab **Hợp đồng** gom hồ sơ theo trạng thái **Đang có hiệu lực**, **Chờ xử lý** và **Lịch sử đã đóng**. Nút **Tái ký** tạo bản nháp có liên kết hợp đồng gốc. Phụ cấp hiển thị số tiền, phần miễn và phần chịu thuế theo cấu hình.

![Chi tiết lương cơ bản, giờ làm tuần và bốn khoản phụ cấp](assets/readme/07-hop-dong-phu-cap.jpg)

<details>
<summary>Xem danh sách hợp đồng, nút tái ký và cấu hình phụ cấp</summary>

**Danh sách hợp đồng**

![Danh sách hợp đồng SMBPlus](assets/readme/06-danh-sach-hop-dong.jpg)

**Hợp đồng theo trạng thái trong hồ sơ**

![Tab hợp đồng với nút Tái ký và các nhóm trạng thái](assets/readme/06a-hop-dong-va-tai-ky.jpg)

**Cấu hình phụ cấp**

![Danh mục phụ cấp và ngưỡng miễn thuế](assets/readme/08-cau-hinh-phu-cap.jpg)

</details>

### 3. Nhập dữ liệu và truy nguồn

Nhân sự nhập hồ sơ từ sheet VP. Công và hiệu quả được nhập theo mapping của từng nguồn, qua bước xem trước rồi mới ghi. Chi tiết batch giúp đối chiếu tập dữ liệu, kỳ, phiên bản và kết quả xử lý.

<details>
<summary>Xem nhập nhân viên, mapping, danh sách và chi tiết đợt nhập</summary>

**Nhập nhân viên**

![Danh sách đợt nhập hồ sơ từ Excel](assets/readme/09-import-nhan-vien.jpg)

**Mapping file**

![Danh sách mapping theo nguồn và kỳ](assets/readme/10-mapping.jpg)

**Các đợt nhập công và hiệu quả**

![Danh sách các đợt nhập](assets/readme/11-dot-import.jpg)

**Chi tiết đợt nhập**

![Chi tiết file nhập, trạng thái và kết quả kiểm tra](assets/readme/12-chi-tiet-import.jpg)

</details>

### 4. Chấm công theo tháng

Mỗi dòng là một nhân viên, mỗi cột ngày là một ô. Lưới hiển thị giờ thường, giờ tăng ca, tổng giờ và ngày công. Kỳ đang mở hỗ trợ nhập ký hiệu trực tiếp; kỳ đang khóa cho xem lịch sử.

![Bảng nhập công theo tháng với giờ thường, tăng ca và ký hiệu](assets/readme/13-bang-cong.jpg)

<details>
<summary>Xem danh mục ký hiệu và báo cáo công lịch sử</summary>

**Ký hiệu chấm công**

![Danh mục ký hiệu với số giờ thường và giờ tăng ca](assets/readme/14-ky-hieu-cong.jpg)

**Báo cáo công các tháng**

![Bảng công lịch sử với bộ lọc và tổng giờ](assets/readme/15-lich-su-cong.jpg)

</details>

### 5. Tính lương, đối chiếu Excel và khóa kỳ

Chọn tháng để xem lương theo công, hiệu quả, làm thêm và khấu trừ. Trong kỳ mở, người có quyền có thể nhập tay một khoản với lý do rồi tính lại hoặc trả ô về công thức. Khóa lương đồng thời khóa công. Bảng Excel có 52 cột và sheet log công thức khi xuất.

![Bảng nhập lương SMBPlus tháng 10/2026](assets/readme/16-bang-luong.jpg)

<details>
<summary>Xem bảng lương Excel, công thức, điều chỉnh, báo cáo và phiếu đối chiếu</summary>

**Bảng lương theo mẫu Excel**

![Bảng lương theo mẫu Excel với bộ lọc tháng và các cột lương](assets/readme/17-luong-mau-excel.jpg)

**Công thức theo ngày hiệu lực**

![Danh sách phiên bản công thức lương](assets/readme/18-cong-thuc.jpg)

**Điều chỉnh lương**

![Màn hình theo dõi điều chỉnh lương](assets/readme/19-dieu-chinh-luong.jpg)

**Báo cáo kết quả lương**

![Báo cáo tổng thu nhập, khấu trừ, thuế và thực nhận](assets/readme/20-bao-cao-luong.jpg)

**Nhật ký lương và phê duyệt**

![Nhật ký nghiệp vụ và truy vết theo bản ghi](assets/readme/21-log-phe-duyet.jpg)

**Điểm vào tổng hợp công và lương**

![Danh sách màn hình tổng hợp theo công ty, năm, tháng và nhân viên](assets/readme/22-tong-hop-thang.jpg)

**Phiếu lương đối chiếu**

![Chi tiết kết quả lương và các thành phần của một nhân viên](assets/readme/23-phieu-luong-doi-chieu.jpg)

**Xem lại tháng 09/2026**

![Bảng lương của kỳ lịch sử tháng 09/2026](assets/readme/24-luong-thang-09.jpg)

</details>

## Chạy tại máy phát triển

Mở Docker Desktop. Từ thư mục gốc, dùng Git Bash hoặc WSL.

```bash
bash setup.sh
bash reload.sh
bash refresh.sh
```

| Lệnh | Khi dùng |
|---|---|
| `setup.sh` | Khởi động lần đầu, dựng image và chạy PostgreSQL cùng Odoo. |
| `reload.sh` | Khởi động lại Odoo sau khi đổi mã nguồn đã gắn vào container. |
| `refresh.sh` | Dựng lại image sau khi đổi Dockerfile hoặc dependency. |
| `docker compose logs -f --tail=100 odoo` | Xem log khi kiểm tra ứng dụng. |

Odoo chạy ở cổng **8069**. `docker-compose.yml` đọc `config/odoo.conf` để xác định DB đang phục vụ. Một máy mới cần dữ liệu demo đã bàn giao hoặc quy trình nạp lại trong tài liệu dev. Thay đổi model, view XML hay phân quyền cần nâng cấp module tương ứng sau khi kiểm thử trên bản sao.

## Tài liệu bàn giao

- [Vòng đời dữ liệu, hướng dẫn sử dụng và 35 testcase nghiệm thu](docs/01_VONG_DOI_DU_LIEU_VA_TESTCASE.md)
- [Hướng dẫn dev xem dữ liệu, truy code, sửa model/view và triển khai](docs/02_HUONG_DAN_DEV.md)

Ảnh chụp trực tiếp từ giao diện SMBPlus. Kho ảnh nằm ở `assets/readme/` để thư mục `docs/` tập trung vào hai tài liệu bàn giao.

# SMBPlus trên Zalo Mini App

## Vận hành trong Odoo

- **Nhân sự → Dashboard nhân sự** hiển thị số nhân viên đang làm, đã liên kết, đơn nghỉ chờ duyệt, số thông báo và sự kiện quan trọng.
- **Nhân sự → Nhân viên → Cấp mã 6 số**. Nhập mã hoặc để trống để hệ thống tự sinh. Gửi riêng mã nhân viên và mã 6 số cho nhân viên. Mã mới dùng lại được đến khi cấp mã khác hoặc thu hồi. Mã tạm cấp ở phiên bản cũ vẫn theo hạn cũ. Tab **Zalo Mini App** hiển thị thông tin liên kết, hạn phiên đăng nhập và nút **Thu hồi quyền truy cập**.
- **Nhân sự → Thông báo Mini App → Mới**. Điền tiêu đề, nội dung, ảnh tùy chọn và đánh dấu sự kiện quan trọng nếu cần. Lưu rồi bấm **Đăng lên Mini App**. Bấm **Gỡ khỏi Mini App** để ngừng hiển thị. Đây là bảng tin trong ứng dụng.
- Nhân viên mở **Nghỉ phép → Tạo ticket** để gửi yêu cầu và **Đơn của tôi** để xem trạng thái. Nhân sự vào **Nhân sự → Dashboard nhân sự → Mở đơn nghỉ chờ duyệt**. Đơn đã duyệt được lưu trong Chấm công → Lịch sử xin nghỉ và điều chỉnh công. Nếu kỳ đang mở và có đủ dữ liệu, hệ thống ghi công ngay. Nếu thiếu dữ liệu hoặc kỳ đã khóa, đơn hiện Chờ ghi công. Sau khi xử lý, mở đơn và bấm Ghi công từ đơn. Nghỉ cả ngày ghi `RO` và đưa giờ về 0. Nghỉ nửa ngày ghi `1/2RO` và trừ nửa số giờ chuẩn của kỳ. Tăng ca ghi `W` và cộng giờ OT. Đi trễ, về sớm và ra ngoài lần lượt ghi `DT`, `VS`, `RN` và trừ giờ thường. Đơn trừ giờ một phần cần có dòng công gốc. Đơn nhiều ngày áp dụng theo ngày lịch, tối đa 31 ngày. Các yêu cầu Mini App này điều chỉnh công và không trừ số dư phép.
- Công hiển thị từ các dòng công đã ghi. Lương hiển thị khi có phiếu chính thức từ kỳ đã chốt. Các kỳ demo mới chỉ tính sẽ hiện trạng thái chưa có phiếu chính thức.

## Chuẩn bị triển khai

1. Addon máy chủ là `hrm_zalo`, phụ thuộc `hrm_data_import` và `hrm_leave`. Cài trên bản sao trước khi áp dụng lên môi trường dùng thật.
2. Chuẩn bị tên miền HTTPS được Zalo cho phép gọi và reverse proxy trỏ đến đúng DB. Giới hạn kích thước yêu cầu, tốc độ tại proxy, không ghi log header Authorization hoặc nội dung mã. API có giới hạn thử mã theo tài khoản Zalo và IP.
3. Trong Odoo, sau khi sẵn sàng kiểm thử, đặt System Parameter **hrm_zalo.enabled** thành chuỗi **True**. Xóa hoặc đổi tham số để tắt API. Quản lý mã cấp, thông báo và dashboard trong Odoo vẫn dùng được khi API tắt.
4. Tạo hoặc liên kết Mini App ID trong [Zalo Mini App Studio](https://docs.zaloplatforms.com/docs/MA/devtools/ide/init). Mở thư mục này, sao chép `.env.example` thành `.env.local`, đặt `VITE_HRM_API_BASE` thành `https://ten-mien-cua-ban/hrm/zalo/v1`. Tệp frontend chỉ cần địa chỉ API.
5. Chạy các lệnh dưới đây. Dùng chức năng Deploy bản Development/Testing trong Studio và kiểm thử trên thiết bị Zalo thật. Mini App đăng nhập bằng mã nhân viên và mã 6 số. Kiểm tra đăng nhập, mở công/lương hai kỳ, gửi đơn nghỉ và xem ảnh thông báo.

```bash
npm ci
npm run dev
npm run build
```

Bản build nằm ở `www/`. Nếu Studio hoặc CLI hỏi **Build folder**, chọn `www`. Khi đổi địa chỉ API, chạy lại `npm run build` trước khi deploy.

[SDK getAccessToken](https://docs.zaloplatforms.com/docs/MA/api/user/user-information/getAccessToken) · [Hướng dẫn xuất bản Zalo](https://docs.zaloplatforms.com/docs/MA/devtools/ide/deploy)

## Hợp đồng API

Prefix `/hrm/zalo/v1`. POST gửi JSON. Gửi Zalo access token hoặc phiên do Odoo cấp trong header `Authorization: Bearer <token>`. Riêng `/login` dùng mã nhân viên và mã 6 số, không cần token Zalo. Phiên này có hạn 8 giờ, chỉ giữ trong bộ nhớ khi Mini App đang mở. Cấp mã mới hoặc thu hồi quyền truy cập sẽ kết thúc phiên cũ. Khi có token Zalo hợp lệ, `/link` lưu liên kết để lần sau mở thẳng hồ sơ.

| Method | Đường dẫn | Dữ liệu |
|---|---|---|
| GET | `/session` | `{linked: boolean}` để quyết định hiện màn hình nhập mã. |
| POST | `/link` | `{employee_code: "NV001", code: "012345"}` và token Zalo hợp lệ. |
| POST | `/login` | Cùng dữ liệu với `/link`. Trả `{session_token}`. Giữ mã 6 số ở dạng chuỗi để giữ số 0 đầu. |
| GET | `/profile` | Mã, tên, công ty, phòng ban, chức vụ, dự án và avatar nếu có. |
| GET | `/periods` | Danh sách kỳ của công ty hiện tại. |
| GET | `/periods/{id}` | Công theo ngày và tổng phiếu lương chính thức nếu có. |
| GET | `/leave` | `options` gồm loại yêu cầu và các mức phút, cùng danh sách đơn của chính người dùng. |
| POST | `/leave` | `{kind, minutes, start, end, reason}`, ngày ISO `YYYY-MM-DD`. `end` dùng cho nghỉ nhiều ngày. |
| GET | `/notices` | Tối đa 10 thông báo đang đăng của công ty, ưu tiên sự kiện quan trọng; ảnh JPG, PNG hoặc WebP. |

Lỗi trả `{error, message}`. Các trạng thái chính là 401 cho token không hợp lệ, 403 khi cần liên kết, 404 khi kỳ ngoài phạm vi, 409 khi đơn trùng, 429 khi vượt giới hạn thử và 503 khi API đang tắt hoặc Zalo chưa phản hồi.

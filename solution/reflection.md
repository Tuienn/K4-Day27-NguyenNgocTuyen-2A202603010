# Thu hoạch Data Siege

**Sinh viên:** Nguyễn Ngọc Tuyền — 2A202603010 — Day 27, Track 2.

## Những lỗi khó phát hiện

Khó nhất là lỗi biên trong chất lượng batch, feature skew và embedding drift:
chúng có thể gần dao động sạch hoặc lệch đồng thời trên nhiều chiều mà chưa
vượt từng ngưỡng riêng. Với batch, tôi kết hợp kiểm tra volume, null, mean và
freshness với khoảng cách tổng hợp. Volume và mean được chuẩn hóa bằng nửa
khoảng baseline (biên 3σ), tránh nhầm với độ lệch chuẩn σ. Với feature, ngưỡng
0,65σ theo hướng dẫn phase.txt cho phép dao động sạch cao hơn baseline lịch sử.
Embedding dùng ngưỡng dịch chuyển 0,040 và tuổi corpus 45 ngày theo dải hướng dẫn.
Đây là các giả định cần hiệu chuẩn lại khi phân phối thay đổi.

Contract có tín hiệu trực tiếp từ violations và SLA; lineage kiểm tra mất
raw.orders/raw.customers, output không có downstream và runtime vượt baseline.
Các kiểm tra cấu trúc này ít phụ thuộc ngưỡng thống kê hơn.

## Đánh đổi chi phí và độ bao phủ

Mỗi sự kiện gọi đúng một tool phù hợp, dùng chung kết quả cho các điều kiện,
không retry hay đọc dữ liệu ngoài API. Tool trả lỗi thì verdict có confidence 0
và lý do thiếu phép đo; không coi lỗi truy xuất là bằng chứng lỗi dữ liệu.
Tôi không bỏ kiểm tra khi budget thấp vì metadata chưa đủ để loại trừ lỗi.
Public dùng 240/220 credits: chấp nhận phạt vượt 9,09% để giữ độ bao phủ.

Practice đạt 50,00 điểm: TP=33, TN=87, FP=0, FN=0; dùng 180/220 credits.
Public đạt 46,90 điểm: TPR=97,44%, FPR=0%, cả bốn pillar đều high.
Private chạy một lần sau khi chốt detector: 32,41 điểm, TPR=64,81%, FPR=0%,
không vượt ngân sách. Private cho thấy độ nhạy với lỗi tinh vi còn hạn chế;
không thể kết luận loại lỗi nào bị bỏ sót từ báo cáo tổng hợp này. Tôi không
sửa ngưỡng theo kết quả Private hay truy cập schedule/key để truy tìm đáp án.

## Cải tiến nếu có thêm thời gian

Tôi sẽ hiệu chuẩn khoảng cách đa chiều bằng tập sạch độc lập và đánh giá
precision/recall trên nhiều luồng được phép thay vì chỉ hạ từng ngưỡng.
Trong ctx.state, có thể giữ cửa sổ thống kê theo bảng/feature/corpus, dùng median
và MAD hoặc EWMA để phát hiện thay đổi kéo dài, có giai đoạn khởi động và chặn
cập nhật từ điểm bất thường để tránh nhiễm baseline. Chỉ áp dụng tiết kiệm tool
khi kiểm chứng được metadata có sức phân biệt; cache phải theo đúng định danh
sự kiện để không dùng số đo cũ thay cho trạng thái mới.

Kiểm chứng: selfcheck đạt 5/5 handler; 9 nhóm unittest bao phủ dữ liệu sạch,
lỗi từng chiều, lệch đa chiều, SLA tùy chọn, biên drift và tool error.

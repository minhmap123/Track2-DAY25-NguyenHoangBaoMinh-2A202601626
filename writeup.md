# Bài viết — Tối ưu chi phí GPU tại NimbusAI

## 1. Chi phí trước và sau khi tối ưu

| | Trước (baseline) | Sau (đã tối ưu) |
|---|---|---|
| Tổng chi phí hàng tháng | $27,133 | $14,626 |
| Giá cho mỗi 1 triệu token (chi phí inference) | $6.49 | $1.13 |

**Tổng cộng tiết kiệm được $12,507/tháng, tương đương 46%.**

Lý do dùng "giá cho mỗi 1 triệu token" thay vì "giá thuê GPU theo giờ": thuê GPU theo giờ chỉ cho biết mình trả bao nhiêu tiền, chứ không cho biết số tiền đó tạo ra được bao nhiêu việc hữu ích. Hai đội trả cùng một mức giá thuê GPU, nhưng đội nào dùng máy hiệu quả hơn thì phục vụ được nhiều yêu cầu hơn với cùng số tiền — nên phải đo theo lượng công việc thực tế làm được (số token) mới phản ánh đúng bức tranh chi phí.

## 2. Từng phần đóng góp vào số tiền tiết kiệm

| Nguồn tiết kiệm | Số tiền/tháng | Tỷ lệ trong tổng tiết kiệm |
|---|---|---|
| Đổi cách thuê máy (thuê giá rẻ có rủi ro / cam kết dài hạn) | $10,040 | 80% |
| Giảm giá xử lý câu hỏi (dùng máy nhỏ khi đủ, nhớ lại phần đã hỏi trước, gộp việc không gấp) | $1,212 | 10% |
| Hạ cấp máy chạy sai hiệu quả xuống loại rẻ hơn | $655 | 5% |
| Tắt máy đang bật nhưng không có việc để làm | $600 | 5% |

**Đổi cách thuê máy là nguồn tiết kiệm lớn nhất** (80%), vì đây là khoản chi phí chiếm tỷ trọng lớn nhất trong hóa đơn gốc — chỉ cần thay đổi cách mua (mua giá rẻ chấp nhận rủi ro bị thu hồi cho việc có thể tạm dừng, hoặc cam kết dùng dài hạn cho việc chạy liên tục) là tiết kiệm ngay mà không cần sửa gì trong code hay hạ tầng.

Còn việc giảm giá xử lý câu hỏi tuy chỉ đóng góp 10% về số tiền tuyệt đối, nhưng lại **giảm giá mỗi triệu token tới 82,6%** (từ $6.49 xuống $1.13) — vì phần chi phí này vốn nhỏ hơn nhiều so với tiền thuê máy trong hóa đơn tổng, nên dù giảm mạnh về tỷ lệ, số tiền tuyệt đối vẫn thấp hơn khoản thuê máy.

## 3. Máy báo "đang bận" nhưng thực ra không làm được nhiều việc

Hai máy trong hệ thống có hiện tượng lạ: đồng hồ báo bận gần như 100% thời gian, nhưng khi đo lượng phép tính thực sự hoàn thành thì rất thấp:

| Máy | % thời gian báo bận | % phép tính thực sự hoàn thành so với khả năng tối đa |
|---|---|---|
| gpu-h100-4 | 98% | 19% |
| gpu-a10g-1 | 97% | 27% |

**Vì sao lại có chuyện này?** Chỉ số "% thời gian báo bận" chỉ cho biết máy có đang chạy hay không, giống như đồng hồ đo xe có nổ máy hay không — nó không đo được xe có đang chở khách trả tiền hay đang kẹt xe không nhúc nhích. Máy có thể "bận" vì đang chờ dữ liệu được chuyển tới (giống công nhân đứng chờ nguyên liệu trên băng chuyền) chứ không phải đang tính toán. Với việc xử lý xử lý câu trả lời từng chữ một (mỗi lần chỉ sinh ra 1 từ), máy phải đọc lại toàn bộ dữ liệu mô hình cho mỗi từ — nên phần lớn thời gian là chờ đọc dữ liệu, không phải tính toán.

**Tác động tài chính:** Doanh nghiệp đang trả tiền thuê máy đầy đủ (theo giờ) cho cả hai máy này, nhưng chỉ nhận được khoảng 1/5 đến 1/4 giá trị tính toán mà lẽ ra máy có thể cho ra. Nếu hạ cấp hai máy này xuống loại máy rẻ hơn có cùng khả năng thực tế, doanh nghiệp tiết kiệm được $655/tháng mà không mất năng lực xử lý thật sự đang dùng.

Ngoài ra, có một máy bị bật nhưng không có việc gì để làm — gây lãng phí $20/ngày, tương đương $600/tháng nếu không tắt.

## 4. Hai phần mở rộng đã thực hiện

### Mở rộng 1 — Tính rủi ro theo từng loại máy khi thuê giá rẻ

**Vấn đề với cách tính cũ:** hệ thống giả định mọi loại máy đều có cùng 5% khả năng bị thu hồi mỗi giờ khi thuê giá rẻ (loại thuê rẻ nhưng có thể bị lấy lại bất cứ lúc nào). Thực tế, máy càng khan hiếm và nhiều người muốn dùng (như H100) càng dễ bị thu hồi hơn máy ít người tranh giành (như A10G, L4).

**Đã sửa:** gán riêng tỷ lệ rủi ro cho từng loại máy (H100: 7%, A100: 5%, A10G: 2%, L4: 1.5%...) rồi tính lại toàn bộ chi phí thuê máy.

**Kết quả đo được:**
- Cách tính cũ (rủi ro đồng đều 5%): tiết kiệm 39.1%
- Cách tính mới (rủi ro theo từng loại máy): tiết kiệm 38.8%

**Bài học:** con số giảm nhẹ vì hai chiều bù trừ nhau — cách tính cũ đã **đánh giá thấp** rủi ro thật của máy H100 (giả định 5% trong khi thực tế 7%, khiến chi phí thuê H100 giá rẻ trông rẻ hơn thực tế) và **đánh giá cao** rủi ro của máy A10G (giả định 5% trong khi thực tế chỉ 2%, khiến chi phí thuê A10G giá rẻ trông đắt hơn thực tế). Dùng một con số chung cho mọi loại máy che giấu mất sự khác biệt này — cần tính riêng theo từng loại máy để ra quyết định mua đúng.

### Mở rộng 2 — Kiểm tra việc nhớ lại câu hỏi cũ có thực sự lời hay không

**Ý tưởng:** việc "nhớ lại" phần câu hỏi đã hỏi trước đó (để không phải tính lại từ đầu) không phải lúc nào cũng lời — vì để "nhớ" được thì hệ thống phải trả thêm một khoản phí ghi nhớ ban đầu. Chỉ khi phần đã nhớ đó được dùng lại đủ nhiều lần thì khoản tiết kiệm mới bù được khoản phí ghi nhớ ban đầu.

**Đã làm:** viết công thức tính "cần nhớ lại tối thiểu bao nhiêu lần thì mới lời", rồi áp dụng vào dữ liệu thực tế (nhóm các câu hỏi theo từng dự án, đếm số lần mỗi dự án lặp lại câu hỏi tương tự làm số lần "nhớ lại" gần đúng).

**Kết quả đo được:**
- Cần tối thiểu **1.39 lần nhớ lại** mới bắt đầu có lời.
- Dự án ít lặp lại nhất trong dữ liệu thực tế cũng có tới **34 lần** — gấp khoảng 24 lần ngưỡng tối thiểu.

**Bài học:** trong trường hợp của NimbusAI hiện tại, việc nhớ lại câu hỏi cũ chắc chắn có lời — không có dự án nào nằm dưới ngưỡng rủi ro. Nhưng nếu sau này có dự án mới với lượng câu hỏi rất ít hoặc không lặp lại (ví dụ mỗi câu hỏi chỉ hỏi đúng 1 lần), cần kiểm tra lại trước khi bật tính năng nhớ lại cho dự án đó, tránh mất tiền oan.

## 5. Ba việc nên làm trước tiên

Nếu là người phụ trách chi phí GPU tại NimbusAI, tôi sẽ ưu tiên theo thứ tự sau — dựa trên số tiền tiết kiệm được so với công sức bỏ ra:

1. **Đổi cách thuê máy trước tiên (ưu tiên cao nhất).** Đây là khoản tiết kiệm lớn nhất ($10,040/tháng, chiếm 80% tổng tiết kiệm) và không cần sửa bất kỳ dòng code nào — chỉ cần đổi hình thức mua máy theo đúng đặc điểm từng công việc (việc chạy liên tục 24/24 → cam kết dài hạn; việc có thể tạm dừng giữa chừng → thuê giá rẻ chấp nhận rủi ro). Làm ngay trong tuần đầu tiên.

2. **Tắt máy đang bật vô ích và hạ cấp hai máy đang "báo bận giả".** Cộng lại tiết kiệm $1,255/tháng, và việc phát hiện chỉ cần theo dõi số liệu có sẵn — không tốn thêm chi phí đầu tư. Nên gắn cảnh báo tự động khi phát hiện máy có hiện tượng tương tự trong tương lai, tránh phải chờ tới cuối tháng mới phát hiện ra.

3. **Áp dụng đủ 3 cách giảm chi phí xử lý câu hỏi (dùng máy nhỏ khi đủ, nhớ lại câu hỏi cũ, gộp việc không gấp).** Tuy đóng góp ít hơn về số tiền tuyệt đối, nhưng giảm giá mỗi triệu token tới 82.6% — đây là khoản tiết kiệm sẽ nhân lên rất lớn khi lượng người dùng tăng trong tương lai, nên cần làm sớm trước khi quy mô lớn hơn khiến việc sửa sau này tốn kém hơn.

---

*Số liệu lấy từ kết quả chạy thực tế các phần M1–M5 và hai phần mở rộng, dữ liệu snapshot tháng 6/2026. Cần cập nhật lại số liệu giá trước khi áp dụng vào thực tế.*

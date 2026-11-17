# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt | dùng |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không đạt (κ và Recall) | loại |

Ma trận nhầm lẫn, FAIL là lớp dương:

| Tiêu chí | TP | FP | FN | TN | Tỉ lệ FAIL quan sát | Tỉ lệ FAIL sau Rogan-Gladen |
|---|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 0.28 | 0.30 |
| helpful | 9 | 0 | 21 | 70 | 0.09 | 0.30 |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | tone H-008: "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người | Judge coi "em", "nha" là thân thiện. Sửa rubric: xưng "LogiX" và "anh/chị", không dùng tiểu từ suồng sã. |
| 2 | tone H-029: "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | Judge chỉ bắt từ khóa "Dạ, vui lòng". Sửa rubric: câu ra lệnh cho khách là FAIL dù có từ lịch sự. |
| 3 | tone H-042: "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì thiếu lời xin lỗi. Sửa rubric: lời xin lỗi không bắt buộc khi reply đủ ý và lịch sự. |
| 4 | tone H-051: "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người | Judge phạt từ tiếng Anh. Sửa rubric: thêm danh sách thuật ngữ CS được phép, gồm "refund". |
| 5 | tone H-063: "Dạ, LogiX đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người | Lỗi là hứa ngoài kết quả hệ thống, thuộc nội dung chứ không thuộc giọng điệu. Tách thành kiểm tra bằng code so với ledger, không giao cho judge tone. |
| 6 | tone H-081: "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | Judge | Nhãn người sai do đọc nhầm ticket. Sửa nhãn thành FAIL; khi đó tone có TP 25, FP 3, P 0.893, R 0.806, κ 0.784. |
| 7 | tone H-088: "Dạ, dạ, LogiX đã hoàn 40.000đ cho đơn O-233 ạ." | FAIL | PASS | Người | Lặp "Dạ" là lỗi gõ. Sửa rubric: lỗi gõ không tính là lỗi giọng điệu. |
| 8 | helpful HL-015: "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." | PASS | FAIL | Người | Ledger ghi 40.000đ. Judge chỉ đọc reply nên không thể biết số tiền sai. |
| 9 | helpful HL-016: reply xin lỗi hai lần, báo hoàn 55.000đ cho đơn O-404 | PASS | FAIL | Người | Ledger ghi 35.000đ. Lời xin lỗi dài làm reply trông hữu ích; số tiền vẫn sai. |
| 10 | helpful HL-047: "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | Sai xưng hô và không nêu kết quả xử lý. Sửa rubric: reply phải nêu số tiền hoặc lý do từ chối. |

## Kết luận
- Loại judge `helpful`, không dùng làm gate. Judge này bỏ sót 21 trên 30 reply lỗi (FN 21, Recall 0.30) và κ 0.375 dưới sàn 0.6. Precision 1.000 chỉ cho biết judge hiếm khi báo FAIL (9 lần), không cho biết judge đáng tin. Trong 21 ca bỏ sót có 18 ca sai số tiền so với ledger và 3 ca sai xưng hô. Nếu dùng judge này làm gate, tỉ lệ lỗi quan sát là 0.09 trong khi tỉ lệ sau hiệu chỉnh là 0.30, nên phần lớn regression về tiền sẽ được merge.
- Sai số tiền là FM-08 và phải chấm bằng code so reply với ledger, không chấm bằng judge.
- Giữ judge `tone_ok` cho tiêu chí giọng điệu, ở mức không chặn merge. Judge sai theo hai hướng: bỏ sót giọng suồng sã hoặc ra lệnh (FN 6) và phạt nhầm reply ngắn hoặc có thuật ngữ được phép (FP 4).
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật.

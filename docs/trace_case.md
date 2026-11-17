# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi nhóm 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `<shape> <claim>@<seed>`, run ID trong report |
| Triệu chứng | Grader nào fail; reply nói gì so với ledger ghi gì |
| Bước sai đầu tiên | Số thứ tự event + kind + trích payload (≤1 dòng) |
| Vì sao là bước *đầu tiên* | Các bước trước đó đúng ra sao (dẫn số event) |
| Failure mode | Mã FM-xx trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng claim@seed trên shape `fixed`: bước đó khác thế nào |
| Regression test | Tên test + grader/assert nào bắt được; đã thấy fail trên variant lỗi và pass trên `fixed` chưa |
| Chưa chắc chắn | Điều trace không chứng minh được |

## Case: `seeded_regression C-014@11`

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-014@11`, run ID `E-seeded_regression-20261117-ccbc` trong `src/reports/eval_seeded_regression.json` (item E-014, seed 11). |
| Triệu chứng | Grader Lab 8 FAIL với lý do `proposal_mismatch`. Reply nói "đã hoàn 120.000đ cho đơn O-515", ledger ghi 90.000đ, nhãn 120.000đ. |
| Bước sai đầu tiên | Event 5 `proposal {"amount_vnd": 120000}`. |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` và event 2 `investigator` giống bản `fixed`. Event 3 `quote` trả 150.000đ, đúng với `proposal_amount` của nhãn. Event 4 `refund_history {"refund_count": 1, "refunded_vnd": 30000}` chỉ đọc dữ liệu và số đọc được là đúng. Event 5 là lúc agent tự trừ 30.000đ khỏi quote. |
| Failure mode | FM-05 (pre_deducted). Host trừ tiếp 30.000đ đã hoàn nên ledger còn 90.000đ. |
| Đối chứng | `fixed C-014@11`: sau event 3 `quote` 150.000đ là event 4 `reply`, không có `refund_history` và `proposal`. Host trừ một lần, ledger 120.000đ, grader Lab 8 PASS. |
| Regression test | `src/tests/test_lab9_trace_case.py`. `test_pre_deducted_proposal_is_caught_on_the_ledger` assert event `proposal` 120.000đ và ledger 90.000đ khác nhãn trên `seeded_regression`. `test_fixed_refunds_the_labelled_amount` assert ledger 120.000đ và không có event `proposal` trên `fixed`. Cả hai đã chạy và pass. |
| Chưa chắc chắn | Trace không ghi lời gọi `issue_refund` của host, nên khoản trừ lần hai chỉ suy ra từ ledger (120.000đ − 90.000đ). Reply báo 120.000đ cũng khác ledger; trace không tách được đây là FM-05 hay FM-08. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.

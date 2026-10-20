# Invoice → CSV สำหรับ NETBAY (V3)

โปรแกรมหน้าเว็บสำหรับงานนำเข้ารถ ทำงาน 4 ขั้น

1. **อัปโหลดไฟล์ invoice** (Excel .xlsx) — รองรับ template `MSFZ`, `JTC`, `AICHI`, `HUAYO`, `JAN TRADING`
2. **ตรวจข้อมูล** — แสดงรถทุกคัน พิกัด เลขเครื่อง และปัญหาที่ต้องแก้ ก่อนบันทึกอะไร
3. **สุ่มเลขเครื่อง + สร้าง CSV** — สุ่มเลข 7 หลักที่ไม่ซ้ำกับที่เคยออก บันทึกลงฐานข้อมูล
   เติมเลขลงไฟล์ Excel และสร้าง CSV สำหรับนำเข้า NETBAY
4. **ส่งเข้า NETBAY** (ถ้าต้องการ) — Playwright เปิด Chrome login สร้างใบขน 610 กรอกหัวใบขน
   แนบ CSV รวมยอด และคำนวณใหม่ แล้วหยุดให้ตรวจและกด Save เอง

## ติดตั้ง (Windows)

ต้องมี Python 3.11+, Google Chrome และ (แนะนำ) Microsoft Excel

```bat
setup.bat ..\db_random_engine.csv
```

- สร้าง `.venv` และติดตั้ง package
- สร้าง `config.ini` จาก `config.example.ini` → **ใส่ username/password ของ NETBAY**
- นำเข้าเลขเครื่องเดิมจากไฟล์ export ของ SQL Server (`APP_RANDOM_ENG`) ลง `data/engine.db`
  (รันซ้ำได้ แถวที่มีแล้วจะข้าม)

## ใช้งาน

ดับเบิลคลิก `run.bat` → เบราว์เซอร์เปิด http://127.0.0.1:5000 เอง

ผลลัพธ์อยู่ใน `output/<วันเวลา>_<BL>/`

| ไฟล์ | คือ |
|---|---|
| `<BL>.csv` | CSV สำหรับนำเข้า NETBAY (TIS-620) |
| `<BL>.xlsx` | invoice ที่เติมเลขเครื่องแล้ว (ต้นฉบับที่อัปโหลดไม่ถูกแก้) |
| `run.json` | สรุปรอบนั้น: รถ เลขเครื่อง พิกัด ยอดรวม คำเตือน |

## เลขเครื่อง (engine number)

- เลขเต็ม = `<หัวเครื่องในไฟล์>-<เลขสุ่ม 7 หลัก>` เช่น `HR15` → `HR15-4810731`
- เลข 7 หลักต้องไม่ซ้ำกับ `RANDOM_ENG` ใดๆ ในฐานข้อมูล (เหมือนโปรแกรมเดิม)
- จองเลขใน transaction เดียวกับการเขียนไฟล์ — ถ้าเขียนไฟล์ไม่สำเร็จ เลขทั้งชุดจะไม่ถูกบันทึก
- ไฟล์ที่มีเลขครบแล้ว (เช่นอัปโหลดไฟล์ Excel ผลลัพธ์ซ้ำ) จะ **ใช้เลขเดิม** ไม่สุ่มต่อท้ายซ้ำ
- ถ้า chassis เคยได้เลขมาก่อน หน้าเว็บจะเตือนพร้อมเลขเดิม
- ฐานข้อมูลคือ SQLite `data/engine.db` ตาราง `APP_RANDOM_ENG`
  (คอลัมน์เดิม + `BL_NO`, `INVOICE_NO`, `SOURCE_FILE`) — **สำรองไฟล์นี้เป็นประจำ**

> ⚠️ ถ้ายังมีเครื่องอื่นใช้โปรแกรมเดิมที่สุ่มเลขลง SQL Server อยู่ เลขของสองฐานข้อมูลอาจชนกันได้
> ควรใช้โปรแกรมนี้เครื่องเดียว หรือ import ข้อมูลจาก SQL Server เข้ามาใหม่ก่อนใช้งาน

## Mapping → CSV

ทุก template มีตารางสรุปตำแหน่งเดียวกัน (สูตรใน template คำนวณไว้) โปรแกรมอ่านจากตรงนั้น

| เซลล์ / คอลัมน์ | ใช้เป็น |
|---|---|
| P4 | ชนิดไฟล์ (MSFZ / JTC / AICHI / HUAYO / JAN TRADING) |
| P5, P6, P14 | invoiceDate, invoiceNo, เลข BL |
| แถว 20+ คอลัมน์ P:U, W:AF | ข้อมูลรถ 1 คันต่อแถว |

| คอลัมน์ CSV | มาจาก |
|---|---|
| invoiceItem | car_no (W) |
| englishDescriptionOfGoods | use_desc_good1 (P) |
| endesc2 | use_desc_good2 (Q) ตัดเลขสุ่มออก เช่น `HR15(GASOLINE/1490),2011` |
| productAttribute2 | เลขเครื่องเต็ม เช่น `HR15-4810731` |
| productAttribute1 | use_chassis_no (R) |
| ins_tariffCode | `0000` + พิกัดจากชีต `datatariff` (ยี่ห้อ+รุ่น+เชื้อเพลิง, ช่วง CC และน้ำหนัก) |
| thaiDescriptionOfGoods | 8703 = รถยนต์เก่า…, 8704 = รถบรรทุกเก่า… (8704 หนักเกิน 5000 กก. → privilege 999 / sequence 65001) |
| originCountry | ตามยี่ห้อใน `data/brand_country.xlsx` ไม่อยู่ในรายการ = JP |
| productCode / productYear / brandName / customsProductCode | `<cc>CC` / year / brand / fuel |
| netWeight, itemGrossWeight / invoiceAmountForeign | use_weight (T) / use_price (U) |
| คอลัมน์อื่น | ค่าคงที่จากแถว 3 ของ `data/csv_template.xlsx` (แก้ในไฟล์นั้นได้เลย) |

ช่องเลขเครื่องที่เติมเลขสุ่ม ([core/layouts.py](core/layouts.py))

| template | ตำแหน่ง |
|---|---|
| MSFZ | คอลัมน์ J (หัวตาราง แถว 19) |
| JTC | คอลัมน์ K |
| AICHI, HUAYO | คอลัมน์ D แถวที่คอลัมน์ C เป็น `ENGINE TYPE` |
| JAN TRADING | คอลัมน์ D แถวที่คอลัมน์ C เป็น `ENGINE NO.` |

เพิ่ม template ใหม่: เพิ่มบรรทัดใน `LAYOUTS` ของ [core/layouts.py](core/layouts.py)
(ไฟล์ต้องมีตารางสรุปแบบเดียวกัน)

## ตรวจก่อนสร้างไฟล์

- ไม่รู้จักชนิดไฟล์ / ไม่มีเลข BL, invoice, วันที่
- จำนวนรถในตารางสรุปไม่เท่ากับในส่วน invoice (สูตรลากไม่ครบ)
- chassis ไม่ตรงกัน, มีตัวอักษรแปลก, use_desc_good2 ไม่ตรงกับเลขเครื่อง (ไฟล์ยังไม่ได้ Save ใน Excel)
- เลขเครื่องในไฟล์ซ้ำกับ chassis อื่นในฐานข้อมูล
- ตัวอักษรที่เข้ารหัส TIS-620 ไม่ได้
- คำเตือน (สร้างไฟล์ได้): ไม่พบพิกัด / เจอหลายพิกัด, ปีหรือ CC ผิดปกติ, chassis ซ้ำในไฟล์, chassis เคยได้เลขแล้ว

## ต่างจากโปรแกรมเดิม

CSV ตรงกับโปรแกรมเดิมทุกคอลัมน์ (ทดสอบเทียบกับโค้ดเดิมแล้ว) ยกเว้นที่ตั้งใจแก้

- ตัวเลขไม่มี `.0` ต่อท้าย (`2004` แทน `2004.0`) และวันที่เป็น `dd/mm/yyyy` เสมอ
- JTC: โปรแกรมเดิมสร้างแถวเกินจากแถวว่างของสูตร (chassis = 0) — V3 ข้ามแถวเหล่านั้น
- AICHI: ถ้าตารางสรุปมีรถน้อยกว่า invoice โปรแกรมเดิมสร้าง CSV ไม่ครบโดยไม่เตือน — V3 แจ้งให้แก้
- เจอหลายพิกัดแต่เป็นพิกัดเดียวกัน → ใช้พิกัดนั้น (เดิมเป็น `0000XXXX`)
- แสดงตัวอย่างก่อนบันทึก และไม่จองเลขถ้างานล้มกลางทาง

## ส่งเข้า NETBAY

ขั้นตอนและ XPath ยกมาจากโปรแกรมเดิม (Selenium) เปลี่ยนเป็น Playwright — [core/netbay.py](core/netbay.py)
ค่าหัวใบขน (เรือ, voyage, ประเทศ, บริษัท) ตั้งใน `config.ini` หัวข้อ `[netbay]`
ทดสอบกับ NETBAY จำลองที่สร้างตามโครงหน้าเว็บเดิม ([tests/mock_netbay.py](tests/mock_netbay.py))

## สร้าง Draft ใบขนจาก ERP-KOLA (worker)

PAINT กด **สร้าง Draft** ที่ ERP-KOLA → งานคงค้าง → 3. Draft ใบขน → งานเข้าคิวพร้อมไฟล์ Final Invoice
`worker.py` รันบนเครื่องในออฟฟิศที่เปิด NETBAY ได้ ถาม ERP เป็นระยะ (ต่อออกไปฝั่งเดียว ไม่ต้องเปิด port) แล้วทำ

1. ตรวจ invoice ตามหัวข้อ "ตรวจก่อนสร้างไฟล์" + เลข BL ต้องตรงกับงาน
   (ไม่พบพิกัด = `XXXX` / เจอหลายพิกัด = `0000XXXX` เหมือนเดิม — แก้ในใบขนบน NETBAY)
2. สุ่มเลขเครื่อง เติมลง Excel และสร้าง CSV (`output/`) — chassis ที่เคยได้เลขใน BL เดียวกันใช้เลขเดิม
3. สร้างใบขนใน NETBAY กรอกหัวใบขน แนบ CSV (Add Invoice → Import)
   **จบเมื่อ NETBAY ขึ้น "success please check your invoice"** — ไม่กด Save / Send to Customs
4. ส่ง **Reference No.** (เช่น `QENX000000019`) และ FN Invoice ที่เติมเลขเครื่องแล้วกลับเข้างาน

ไม่ผ่านข้อไหน งานใน ERP ขึ้น "สร้าง Draft ไม่สำเร็จ" พร้อมเหตุผล แก้ไฟล์แล้วกดสร้างใหม่ได้
ถ้า NETBAY ล้มกลางทาง หรือไม่ขึ้นข้อความ success ภายใน 3 นาที เหตุผลจะบอกเลขใบขนที่สร้างค้างไว้
และข้อความที่ NETBAY แสดงอยู่

ตั้งค่าใน `config.ini`

```ini
[erp]
url = https://erp-kola.vercel.app
api_key = <WORKER_API_KEY ตัวเดียวกับบน Vercel>
```

เปิดด้วย `run_worker.bat` (หรือ `python worker.py`, ทดสอบ 1 งาน: `--once`)
แท็บ Draft ใบขนบน ERP บอกว่า worker ออนไลน์อยู่ไหม ทำงานไหนอยู่

## เปิดใบขนจากเลข Ref No. บน ERP-KOLA

เลข Ref No. ในทุกหน้าของ ERP (รวมหน้าตรวจ Draft ของ FAH) เป็นลิงก์ `kola-netbay://open?ref=<Ref No.>`
กดแล้ว imp ในเครื่องนั้นเปิด Chrome → login → Import → ค้นหา Ref No. → เปิดใบขน แล้วปล่อยหน้าต่างไว้ให้ตรวจต่อ
(ลิงก์ตรงไปหน้าใบขนใช้ไม่ได้ เพราะ NETBAY ผูก session ไว้กับเบราว์เซอร์ที่ login)

ติดตั้งครั้งเดียวต่อเครื่อง — เครื่องต้องมี imp + `config.ini` ที่ใส่ user/pass NETBAY และอยู่ในเครือข่ายออฟฟิศ

| เครื่อง | ติดตั้ง |
|---|---|
| Windows | ดับเบิลคลิก `install\windows-netbay-launcher.cmd` |
| Mac | `bash install/mac-netbay-launcher.sh` |

ทดสอบโดยไม่ผ่าน ERP: `python open_ref.py QENX000000020` · log: `work/open_ref.log`

## โครงสร้าง

```
app.py               หน้าเว็บ (Flask)
web/index.html       หน้าจอ
core/invoice.py      อ่าน invoice
core/layouts.py      ตำแหน่งข้อมูลแต่ละ template
core/tariff.py       หาพิกัด
core/engine_db.py    ฐานข้อมูลเลขเครื่อง (SQLite)
core/excel_out.py    เติมเลขเครื่องลง Excel (Microsoft Excel หรือ openpyxl)
core/netbay_csv.py   mapping → CSV
core/pipeline.py     รวมขั้นตอน ตรวจ → สุ่มเลข → เขียนไฟล์
core/netbay.py       ส่งเข้า NETBAY (Playwright)
worker.py            รับงานสร้าง Draft ใบขนจาก ERP-KOLA
open_ref.py          เปิดใบขนจาก Ref No. (ลิงก์ kola-netbay:// บน ERP-KOLA)
install/             ตัวติดตั้งลิงก์ kola-netbay:// (Mac / Windows)
tools/import_db.py   นำเข้าเลขเครื่องเดิมจาก SQL Server export
```

## ทดสอบ

```bat
.venv\Scripts\python -m pytest
```

ใช้ invoice สมมติที่สร้างในเทสต์ + NETBAY จำลอง
ถ้าวาง MASTER template จริงไว้ใน `tests/fixtures/` (ไม่อยู่ใน git) จะทดสอบกับไฟล์จริงด้วย

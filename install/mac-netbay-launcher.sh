#!/bin/bash
#
# ติดตั้งตัวเปิดใบขนบน Mac — ให้เลข Ref No. บน ERP-KOLA กดแล้วเปิดใบขนใน NETBAY ได้
#
# สร้างแอป ~/Applications/KOLA NETBAY.app ที่รับลิงก์ kola-netbay://open?ref=<Reference No.>
# กดลิงก์แล้วแอปนี้รัน open_ref.py ของ imp: เปิด Chrome -> login -> Import -> ค้นหา Ref No. -> เปิดใบขน
# ใช้ username/password NETBAY จาก config.ini ของ imp ในเครื่องนี้ · log: ~/Library/Logs/KOLA/netbay-open.log
#
# วิธีใช้ (ในโฟลเดอร์ imp):  bash install/mac-netbay-launcher.sh
# ย้ายโฟลเดอร์ imp ไปที่อื่นแล้วต้องรันใหม่ เพราะแอปจำที่อยู่โฟลเดอร์ไว้
set -euo pipefail

IMP="$(cd "$(dirname "$0")/.." && pwd)"
APP="$HOME/Applications/KOLA NETBAY.app"
PY="$IMP/.venv/bin/python"
LOG_DIR="$HOME/Library/Logs/KOLA"

[ -x "$PY" ] || { echo "ไม่พบ $PY — ติดตั้ง imp ก่อน (python3 -m venv .venv && .venv/bin/pip install -r requirements.txt)"; exit 1; }
"$PY" -c "from core import config; s = config.load().netbay; assert s.username and s.password" 2>/dev/null \
  || echo "⚠️  ยังไม่มี username/password ของ NETBAY ใน $IMP/config.ini — เปิดใบขนไม่ได้จนกว่าจะใส่"

SCRIPT="$(mktemp -t kola-netbay).applescript"
cat > "$SCRIPT" <<APPLESCRIPT
on open location theURL
  openRef(theURL)
end open location

on run
  display dialog "กดเลข Ref No. บน ERP-KOLA เพื่อเปิดใบขนใน NETBAY" buttons {"ตกลง"} default button 1 with title "KOLA NETBAY"
end run

on openRef(theURL)
  try
    do shell script "mkdir -p " & quoted form of "$LOG_DIR" & "; cd " & quoted form of "$IMP" & " && nohup " & quoted form of "$PY" & " open_ref.py " & quoted form of theURL & " >> " & quoted form of "$LOG_DIR/netbay-open.log" & " 2>&1 < /dev/null &"
  on error errMsg number errNum
    display dialog "เปิดใบขนไม่สำเร็จ: " & errMsg & " (" & errNum & ")" & return & return & "ดู log ได้ที่ $LOG_DIR/netbay-open.log" buttons {"ตกลง"} default button 1 with title "KOLA NETBAY" with icon caution
  end try
end openRef
APPLESCRIPT

mkdir -p "$HOME/Applications"
rm -rf "$APP"
osacompile -o "$APP" "$SCRIPT"
rm -f "$SCRIPT"

PLIST="$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy \
  -c "Set :CFBundleIdentifier th.co.kola.netbay-opener" \
  -c "Add :CFBundleURLTypes array" \
  -c "Add :CFBundleURLTypes:0 dict" \
  -c "Add :CFBundleURLTypes:0:CFBundleURLName string KOLA NETBAY" \
  -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes array" \
  -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string kola-netbay" \
  "$PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string th.co.kola.netbay-opener" "$PLIST"

# แก้ Info.plist แล้วลายเซ็นเดิมใช้ไม่ได้ ต้องเซ็นใหม่ ไม่งั้น macOS ไม่ยอมเปิด
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP"

echo "✅ ติดตั้งแล้ว: $APP"
echo "   กดเลข Ref No. บน ERP-KOLA แล้วจะเปิดใบขนใน NETBAY ด้วย imp ใน $IMP"
echo "   log: $LOG_DIR/netbay-open.log"
echo "   ครั้งแรกเบราว์เซอร์จะถามว่าจะเปิด KOLA NETBAY ไหม — ติ๊กอนุญาตเสมอแล้วกดเปิด"

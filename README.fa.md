# راه‌اندازی Xray MITM Domain Fronting روی OpenWrt

**راهنما:** [English](README.md) | فارسی

**پروژه:** [فهرست تغییرات](CHANGELOG.md) | [راهنمای مشارکت](CONTRIBUTING.md)

این پروژه سرویس مستقل Xray MITM-DomainFronting، صفحه مدیریتی LuCI و اتصال اختیاری به مسیریابی PassWall2 را برای OpenWrt رسمی سری 25.12 فراهم می‌کند.

> [!CAUTION]
> CA مورد اعتماد MITM می‌تواند ترافیک HTTPS دستگاه‌هایی را که به آن اعتماد دارند رمزگشایی کند. فقط روی شبکه و دستگاه‌هایی استفاده کنید که مالک آن‌ها هستید یا اجازه مدیریتشان را دارید. فقط `mycert.crt` را روی کلاینت نصب کنید. `mycert.key` باید روی روتر و در نسخه پشتیبان محافظت‌شده بماند.

## از اینجا شروع کنید

feed عمومی فعلی برای OpenWrt رسمی **نسخه 25.12.5 و نسخه‌های نگهداری جدیدتر از سری 25.12** است. روتر باید از مدیر بسته `apk` استفاده کند و به GitHub و GitHub Pages دسترسی داشته باشد.

### ۱. نصب یا به‌روزرسانی با یک دستور

اگر آدرس روتر متفاوت است، `192.168.1.1` را تغییر دهید. وقتی درخواست شد رمز روتر را وارد کنید.

**MAC:**

```sh
ssh root@192.168.1.1 'wget -qO /tmp/install-xray-mitm.sh https://duuuude.github.io/xray-mitm-openwrt/install.sh && printf "%s  %s\n" "8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405" "/tmp/install-xray-mitm.sh" | sha256sum -c - && sh /tmp/install-xray-mitm.sh'
```

**WINDOWS PC (PowerShell):**

```powershell
ssh.exe root@192.168.1.1 'wget -qO /tmp/install-xray-mitm.sh https://duuuude.github.io/xray-mitm-openwrt/install.sh && printf "%s  %s\n" "8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405" "/tmp/install-xray-mitm.sh" | sha256sum -c - && sh /tmp/install-xray-mitm.sh'
```

اگر از قبل با SSH داخل روتر هستید:

**ROUTER:**

```sh
wget -qO /tmp/install-xray-mitm.sh https://duuuude.github.io/xray-mitm-openwrt/install.sh && printf '%s  %s\n' '8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405' '/tmp/install-xray-mitm.sh' | sha256sum -c - && sh /tmp/install-xray-mitm.sh
```

دستور، فایل نصب‌کننده عمومی را پیش از اجرا بررسی می‌کند. SHA-256 ثابت آن `8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405` است.

همین دستور هم نصب اولیه و هم به‌روزرسانی‌های بعدی را انجام می‌دهد. نصب‌کننده:

1. نسخه OpenWrt و مدیر بسته را بررسی می‌کند.
2. کلید عمومی feed را با HTTPS دریافت می‌کند.
3. فقط در صورت تطبیق دقیق fingerprint زیر، کلید را می‌پذیرد:

   ```text
   3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a
   ```

4. feed امضاشده را به APK اضافه و فایل‌های آن را برای ارتقای firmware نگه می‌دارد.
5. داخل `/root/` یک نسخه پشتیبان محافظت‌شده می‌سازد.
6. از APK می‌خواهد امضا را بررسی و فقط بسته‌های `xray-mitm` و `luci-app-xray-mitm` را نصب یا به‌روزرسانی کند.

نصب‌کننده از `--allow-untrusted` استفاده نمی‌کند، همه بسته‌های روتر را یک‌جا ارتقا نمی‌دهد، CA نمی‌سازد، سرویس را روشن نمی‌کند و مسیریابی PassWall2 را تغییر نمی‌دهد.

### ۲. راه‌اندازی اولیه در LuCI

LuCI را با **HTTPS** باز کنید و به **Services → MITM Domain Fronting** بروید.

1. **Install packaged default configuration** را انتخاب کنید.
2. **Generate candidate** را انتخاب کنید؛ یا یک گواهی و کلید خصوصی منطبق که در اختیار خودتان است وارد کنید.
3. **Activate candidate** را انتخاب کنید.
4. فقط `mycert.crt` را دانلود کنید.
5. `mycert.crt` را روی کلاینت‌هایی که باید از MITM استفاده کنند به‌عنوان Root CA مورد اعتماد نصب کنید.
6. **Start** را انتخاب و **Health check** را اجرا کنید؛ نتیجه باید PASS باشد.
7. برای اجرای خودکار بعد از ریبوت، **Enable at boot** را فعال کنید.

CA عمومی را برای کاربر فعلی نصب کنید:

**MAC:**

```sh
security add-trusted-cert -r trustRoot \
  -k "$HOME/Library/Keychains/login.keychain-db" ./mycert.crt
```

**WINDOWS PC (PowerShell):**

```powershell
certutil.exe -user -addstore -f Root .\mycert.crt
```

ممکن است Firefox از certificate store جدا استفاده کند؛ در این حالت `mycert.crt` را داخل Firefox هم وارد کنید. `mycert.key` را هرگز روی کلاینت کپی نکنید.

### ۳. مسیریابی دامنه‌های انتخابی با PassWall2

اگر فقط SOCKS محلی را می‌خواهید، این مرحله را رد کنید.

1. بخش PassWall2 را در صفحه LuCI پروژه باز کنید.
2. shunt node و VPN node موجود را انتخاب کنید.
3. **Preview changes** را بزنید.
4. node محلی، دامنه‌ها، مقصدها و ترتیب قوانین را بررسی کنید.
5. فقط وقتی preview درست است **Apply preview** را انتخاب کنید.

دستیار حداکثر سه قانون مدیریت‌شده می‌سازد و آن‌ها را به این ترتیب قرار می‌دهد:

1. **VPN Overrides** بسته‌های انتخابی Gemini، بررسی اتصال Android، کنترل YouTube و ورود Google Account را به VPN انتخاب‌شده می‌فرستد. دامنه تحویل ویدئو یعنی `googlevideo.com` عمداً در این قانون نیست.
2. **MITM-Compatible Services** بسته‌های انتخابی Google، وب‌سایت‌های Meta و سایت‌های مبتنی بر Fastly را به SOCKS محلی `127.0.0.1:10808` می‌فرستد. Google پیشنهاد پیش‌فرض است؛ Meta و Fastly تا زمان آزمایش روی دستگاه‌های شما خاموش می‌مانند.
3. **Regional Direct Access** دامنه‌ها و IPهای ایران را مستقیم می‌فرستد.

هر checkbox فقط یک مجموعه دامنه را به یکی از همین سه قانون اضافه می‌کند و قانون جداگانه‌ای نمی‌سازد. اولین اعمال مدل سه‌قانونی، قوانین قدیمی مدیریت‌شده توسط بسته را مهاجرت می‌دهد. قوانین قدیمی ساخته‌شده توسط کاربر بدون تغییر باقی می‌مانند، ولی اتصال آن‌ها به shunt انتخابی حذف می‌شود تا تطبیق تکراری رخ ندهد. برای جلوگیری از loop، مقدار `localhost_proxy=0` را نگه دارید.

### ۴. بررسی از دستگاه کلاینت

**MAC:**

```sh
for url in \
  https://www.google.com \
  https://www.youtube.com \
  https://www.cloudflare.com \
  https://gemini.google.com
do
  printf '\n%s\n' "$url"
  curl -Iv --max-time 20 "$url" 2>&1 |
    grep -E 'issuer:|^HTTP/'
done
```

**WINDOWS PC (PowerShell):**

```powershell
$urls = @(
  'https://www.google.com',
  'https://www.youtube.com',
  'https://www.cloudflare.com',
  'https://gemini.google.com'
)

foreach ($url in $urls) {
  Write-Host "`n$url"
  curl.exe -Iv --max-time 20 $url 2>&1 |
    Select-String -Pattern 'issuer:', 'HTTP/'
}
```

دامنه‌ای که از MITM عبور می‌کند باید این issuer را نشان دهد:

```text
issuer: CN=MITM-DomainFronting
```

دامنه‌های VPN یا direct باید CA عمومی عادی خود را نشان دهند. پاسخ HTTP دامنه‌های مورد انتظار نیز باید موفق باشد.

## به‌روزرسانی‌های بعدی

ساده‌ترین روش، اجرای دوباره همان دستور نصب یک‌خطی است. بعد از تنظیم feed می‌توانید مستقیماً روی روتر نیز به‌روزرسانی کنید:

**ROUTER:**

```sh
apk update
apk upgrade xray-mitm luci-app-xray-mitm
```

این دستور فقط همین دو بسته انتخاب‌شده و وابستگی‌های لازم آن‌ها را ارتقا می‌دهد. از اجرای `apk upgrade` بدون نام بسته‌ها به‌عنوان جایگزین ارتقای firmware استفاده نکنید.

به‌روزرسانی، `/etc/config/xray-mitm`، پوشه `/etc/xray-mitm/`، CA فعال، وضعیت سرویس و تنظیمات PassWall2 را حفظ می‌کند. قبل از تغییر feed یا بسته‌ها، نصب‌کننده فایل پشتیبان `/root/xray-mitm-before-install-YYYYMMDD-HHMMSS.tar.gz` را با سطح دسترسی `0600` می‌سازد.

## روش احراز اصالت

در اجرای اول، نصب‌کننده با HTTPS از GitHub دریافت می‌شود و fingerprint کلید عمومی feed را در خود دارد. APK با این کلید، امضای index و همه بسته‌ها را بررسی می‌کند. به‌روزرسانی‌های بعدی نیز از همان کلید ذخیره‌شده و feed امضاشده استفاده می‌کنند.

- build عادی pull request هیچ secretی ندارد و فقط artifact توسعه‌ای بدون کلید امضای production و بدون secret می‌سازد.
- tag انتشار باید دقیقاً با نسخه بسته یکی باشد.
- امضای production فقط در GitHub environment محافظت‌شده `signed-feed` انجام می‌شود.
- workflow ابتدا تطبیق کلید خصوصی محافظت‌شده با کلید عمومی commit‌شده را بررسی می‌کند.
- SDK رسمی OpenWrt فایل `packages.adb` و APKهای امضاشده را می‌سازد.
- feed در GitHub Pages و فایل‌های همان نسخه در GitHub Release منتشر می‌شوند.

کلید خصوصی production داخل repository یا package قرار نمی‌گیرد. جزئیات انتشار، بازیابی و تعویض کلید در [راهنمای عملیات feed امضاشده](docs/SIGNED_FEED.md) آمده است.

## نیازمندی‌ها و رفتار امن

بسته‌ها `all` هستند، ولی feed فعلی برای اکوسیستم APK در OpenWrt 25.12 آزمایش می‌شود. نصب اولیه عمداً غیرفعال است: CA ساخته نمی‌شود، startup فعال نمی‌شود، Xray اجرا نمی‌شود و firewall، DNS و PassWall2 تغییر نمی‌کنند.

listenerها فقط روی localhost هستند:

| کاربرد | آدرس |
| --- | --- |
| ورودی محلی mixed/SOCKS | `127.0.0.1:10808` |
| تونل رمزگشایی TLS برای HTTP/1.1 | `127.0.0.1:11666` |
| تونل رمزگشایی TLS برای HTTP/2 | `127.0.0.1:11777` |

## نصب دستی احرازشده

اگر روتر به GitHub Pages دسترسی ندارد، دو APK، فایل `xray-mitm-feed-v1.pem`، فایل `PUBLIC_KEY_SHA256` و `SHA256SUMS` را از یک GitHub Release امضاشده واحد روی مک یا ویندوز دریافت کنید.

**ROUTER:**

```sh
mkdir -p -m 0700 /tmp/xray-mitm-install
```

**MAC:**

```sh
cd "/path/to/downloaded/release-files"
scp -O xray-mitm-*.apk luci-app-xray-mitm-*.apk \
  xray-mitm-feed-v1.pem PUBLIC_KEY_SHA256 SHA256SUMS \
  root@192.168.1.1:/tmp/xray-mitm-install/
```

**WINDOWS PC (PowerShell):**

```powershell
Set-Location "C:\path\to\downloaded\release-files"
scp.exe -O .\xray-mitm-*.apk .\luci-app-xray-mitm-*.apk `
  .\xray-mitm-feed-v1.pem .\PUBLIC_KEY_SHA256 .\SHA256SUMS `
  root@192.168.1.1:/tmp/xray-mitm-install/
```

قبل از نصب کلید، fingerprint را با مقدار این README مقایسه کنید. اگر متفاوت بود ادامه ندهید.

**ROUTER:**

```sh
cd /tmp/xray-mitm-install
printf '%s  %s\n' \
  '3e0dc07ffef69d1512500b6add486381d8c261a8ec3fcce54fa403b35320df8a' \
  'xray-mitm-feed-v1.pem' | sha256sum -c -
awk '$2 ~ /[.]apk$/' SHA256SUMS | sha256sum -c -
mkdir -p /etc/apk/keys
cp xray-mitm-feed-v1.pem /etc/apk/keys/xray-mitm-feed-v1.pem
chmod 0644 /etc/apk/keys/xray-mitm-feed-v1.pem
apk add ./xray-mitm-*.apk ./luci-app-xray-mitm-*.apk
```

artifactهای توسعه‌ای CI خارج از مسیر اعتماد production هستند و نباید به‌عنوان انتشار امضاشده به کاربر تازه‌کار داده شوند.

## آزمایش توسعه و انتشار

برای روند branch محلی و pull request، [راهنمای مشارکت](CONTRIBUTING.md) و برای
تاریخچه تغییرات قابل مشاهده کاربران، [فهرست تغییرات](CHANGELOG.md) را ببینید.

**MAC:**

```sh
cd "/path/to/xray-mitm-openwrt"
sh scripts/validate-release.sh
```

**WINDOWS PC (PowerShell with WSL):**

```powershell
wsl.exe sh -lc 'cd /path/to/xray-mitm-openwrt && sh scripts/validate-release.sh'
```

قبل از انتشار tag، [راهنمای آزمایش انتشار](docs/RELEASE_TESTING.md) را اجرا کنید.

## حذف

ابتدا سرویس را متوقف و startup را غیرفعال کنید. اگر مسیریابی PassWall2 اعمال شده، rollback را از LuCI اجرا کنید. سپس:

**ROUTER:**

```sh
/etc/init.d/xray-mitm stop
/etc/init.d/xray-mitm disable
apk del luci-app-xray-mitm xray-mitm
```

بعد از پایان استفاده، `mycert.crt` را از trust store همه کلاینت‌ها حذف کنید. `mycert.key` و نسخه‌های پشتیبان روتر همچنان محرمانه هستند.

این پروژه مستقل از Xray-core، OpenWrt، LuCI و PassWall2 است. مجوزها و attribution در [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) آمده است.

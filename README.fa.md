# راه‌اندازی Xray MITM Domain Fronting روی OpenWrt

**راهنما:** [English](README.md) | فارسی

این پروژه یک سرویس مستقل Xray به‌همراه صفحه مدیریتی LuCI برای MITM-DomainFronting روی OpenWrt فراهم می‌کند. بسته‌های منتشرشده برای OpenWrt رسمی نسخه 25.12.5 یا جدیدتر با مدیر بسته APK ساخته شده‌اند.

> [!CAUTION]
> گواهی ریشه MITM می‌تواند ترافیک HTTPS دستگاه‌هایی را که به آن اعتماد کرده‌اند رمزگشایی کند. فقط روی شبکه و دستگاه‌هایی استفاده کنید که مالک آن‌ها هستید یا اجازه صریح مدیریتشان را دارید. کلید خصوصی `mycert.key` را هرگز منتشر یا برای شخص دیگری ارسال نکنید.

## راه‌اندازی سریع

### ۱. نصب با یک دستور

بسته‌های منتشرشده به OpenWrt رسمی 25.12.5 یا جدیدتر با APK و بسته سازگار `xray-core` نیاز دارند. اگر آدرس روتر شما متفاوت است، `192.168.1.1` را تغییر دهید. سپس دستور مربوط به کامپیوتر خود را اجرا و رمز روتر را وارد کنید.

**مک:**

```sh
ssh root@192.168.1.1 'wget -qO /tmp/install-xray-mitm.sh https://raw.githubusercontent.com/duuuude/xray-mitm-openwrt/main/install.sh && sh /tmp/install-xray-mitm.sh'
```

**کامپیوتر ویندوزی (PowerShell):**

```powershell
ssh.exe root@192.168.1.1 "wget -qO /tmp/install-xray-mitm.sh https://raw.githubusercontent.com/duuuude/xray-mitm-openwrt/main/install.sh && sh /tmp/install-xray-mitm.sh"
```

اگر از قبل با SSH وارد روتر شده‌اید، دستور کوتاه‌تر زیر را اجرا کنید:

**روتر:**

```sh
wget -qO /tmp/install-xray-mitm.sh https://raw.githubusercontent.com/duuuude/xray-mitm-openwrt/main/install.sh && sh /tmp/install-xray-mitm.sh
```

نصب‌کننده روتر را بررسی می‌کند، آخرین GitHub Release را دریافت می‌کند، checksum هر دو APK را با `SHA256SUMS` می‌سنجد، هنگام ارتقا یک نسخه پشتیبان محافظت‌شده می‌سازد و بسته اصلی و LuCI را نصب می‌کند. این برنامه CA نمی‌سازد، سرویس را روشن نمی‌کند و مسیریابی PassWall2 را تغییر نمی‌دهد. این کارها همچنان به‌صورت شفاف در LuCI انجام می‌شوند.

روتر باید به `raw.githubusercontent.com` و `github.com` از طریق HTTPS دسترسی داشته باشد. اگر این آدرس‌ها از روتر باز نمی‌شوند، از روش دستی زیر استفاده کنید تا فایل‌ها روی مک یا کامپیوتر ویندوزی دانلود و با SSH به روتر منتقل شوند.

<details>
<summary>روش دستی: دریافت و کپی فایل‌های انتشار</summary>

ابتدا وجود APK و نسخه روتر را بررسی کنید:

**روتر:**

```sh
. /etc/openwrt_release
printf 'OpenWrt release: %s\n' "$DISTRIB_RELEASE"
apk --version
```

از یک GitHub Release واحد، این سه فایل را دانلود کنید:

- `xray-mitm-*.apk`
- `luci-app-xray-mitm-*.apk`
- `SHA256SUMS`

ابتدا روی روتر یک پوشه موقت محافظت‌شده بسازید.

**روتر:**

```sh
mkdir -p -m 0700 /tmp/xray-mitm-install
```

سپس در مک وارد پوشه فایل‌های دانلودشده شوید و آن‌ها را به روتر بفرستید. گزینه `-O` برای Dropbear روتر از روش قدیمی SCP استفاده می‌کند.

**مک:**

```sh
cd "/path/to/downloaded/release-files"
scp -O xray-mitm-*.apk luci-app-xray-mitm-*.apk SHA256SUMS \
  root@192.168.1.1:/tmp/xray-mitm-install/
```

اگر آدرس روتر شما متفاوت است، `192.168.1.1` را تغییر دهید.

**کامپیوتر ویندوزی (PowerShell):**

در Windows 10 و 11 می‌توانید از قابلیت اختیاری **OpenSSH Client** استفاده کنید. ابتدا وجود `ssh.exe` و `scp.exe` را بررسی و سپس همان سه فایل را کپی کنید:

```powershell
Get-Command ssh.exe, scp.exe
Set-Location "C:\path\to\downloaded\release-files"
$core = (Get-ChildItem -File 'xray-mitm-*.apk').FullName
$luci = (Get-ChildItem -File 'luci-app-xray-mitm-*.apk').FullName
$sums = (Resolve-Path '.\SHA256SUMS').Path
scp.exe -O $core $luci $sums root@192.168.1.1:/tmp/xray-mitm-install/
```

اگر `Get-Command` این برنامه‌ها را پیدا نکرد، ابتدا **OpenSSH Client** را از Optional Features ویندوز نصب کنید. اگر آدرس روتر متفاوت است، `192.168.1.1` را تغییر دهید.

checksum را بررسی و بسته‌ها را نصب کنید

قبل از نصب، checksum هر دو بسته را بررسی کنید. اگر هرکدام خطا داد، نصب را ادامه ندهید.

**روتر:**

```sh
cd /tmp/xray-mitm-install
sha256sum -c SHA256SUMS
apk update
apk add --allow-untrusted ./xray-mitm-*.apk ./luci-app-xray-mitm-*.apk
```

بسته‌های CI با کلیدی که روتر معمولی به آن اعتماد دارد امضا نشده‌اند؛ به همین دلیل پس از بررسی checksum از `--allow-untrusted` استفاده می‌شود.

</details>

### ۲. پیکربندی اولیه در LuCI

نصب بسته به‌تنهایی سرویس را روشن نمی‌کند، CA نمی‌سازد و مسیریابی PassWall2 را تغییر نمی‌دهد.

1. LuCI را با **HTTPS** باز کنید.
2. به **Services → MITM Domain Fronting** بروید.
3. گزینه **Install packaged default configuration** را انتخاب کنید.
4. برای ساخت CA جدید، **Generate candidate** را انتخاب کنید. همچنین می‌توانید یک جفت گواهی و کلید خصوصی منطبق که در اختیار خودتان است وارد کنید.
5. گزینه **Activate candidate** را انتخاب کنید.
6. فقط فایل عمومی `mycert.crt` را دانلود کنید.
7. `mycert.crt` را روی دستگاه‌هایی که باید از MITM استفاده کنند به‌عنوان Root CA مورد اعتماد نصب کنید.
8. در LuCI سرویس را **Start** کنید و **Health check** را اجرا کنید. نتیجه باید PASS باشد.
9. اگر سرویس باید بعد از ریبوت خودکار اجرا شود، **Enable at boot** را فعال کنید.

فایل `mycert.key` باید فقط روی روتر و نسخه‌های پشتیبان محافظت‌شده باقی بماند. آن را روی کلاینت نصب نکنید.

CA عمومی دانلودشده را برای حساب کاربری‌ای که از سرویس استفاده می‌کند نصب کنید:

**مک:**

```sh
security add-trusted-cert -r trustRoot \
  -k "$HOME/Library/Keychains/login.keychain-db" ./mycert.crt
```

**کامپیوتر ویندوزی (PowerShell):**

```powershell
certutil.exe -user -addstore -f Root .\mycert.crt
```

دستور ویندوز CA را فقط برای کاربر فعلی trusted می‌کند. اگر Firefox از certificate store مستقل استفاده کند، باید `mycert.crt` را داخل خود Firefox نیز وارد کنید.

### ۳. اتصال اختیاری به PassWall2

اگر فقط خود سرویس و پراکسی محلی را می‌خواهید، این مرحله لازم نیست. برای مسیریابی شفاف دامنه‌ها:

1. بخش PassWall2 را در صفحه LuCI پروژه باز کنید.
2. Shunt node و VPN node مناسب را انتخاب کنید.
3. ابتدا **Preview changes** را اجرا کنید.
4. node محلی، دامنه‌ها، مقصد هر قانون و ترتیب قوانین را بررسی کنید.
5. فقط بعد از بررسی، **Apply preview** را انتخاب کنید.

ترتیب قوانین مهم است و قانون بالاتر اول اجرا می‌شود. یک دامنه در قوانین بالاتر مانند `Android_Check`، `Gemini_VPN` یا `YouTube_Control_VPN` می‌تواند قانون `Google_MITM` را بی‌اثر کند.

- اگر `www.google.com` باید از MITM عبور کند، آن را در قانون VPN بالاتر مانند `Android_Check` قرار ندهید.
- برای عبور بخش کنترل YouTube از VPN می‌توانید `YouTube_Control_VPN` را فعال کنید.
- اگر ویدیوهای YouTube باید از مسیر سریع MITM عبور کنند، `googlevideo.com` را در `YouTube_Control_VPN` قرار ندهید؛ این دامنه باید در `Google_MITM` باقی بماند.
- گزینه `localhost_proxy=0` مانع ورود دوباره خروجی Xray مستقل به PassWall2 و ایجاد حلقه می‌شود.

### ۴. آزمایش از دستگاه کلاینت

پس از نصب `mycert.crt` روی مک، این آزمایش را اجرا کنید:

**مک:**

```sh
curl -Iv --max-time 20 https://www.google.com 2>&1 |
  grep -E 'issuer:|^HTTP/'
```

**کامپیوتر ویندوزی (PowerShell):**

```powershell
curl.exe -Iv --max-time 20 https://www.google.com 2>&1 |
  Select-String -Pattern 'issuer:', 'HTTP/'
```

اگر Google به `Google_MITM` متصل باشد، باید این issuer دیده شود:

```text
issuer: CN=MITM-DomainFronting
```

همچنین پاسخ HTTP باید موفق باشد. دامنه‌ای که در قانون MITM قرار ندارد باید گواهی عمومی عادی خود را نشان دهد.

برای بررسی چند مسیر:

**مک:**

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

**کامپیوتر ویندوزی (PowerShell):**

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

نتیجه دقیق به قوانین شما بستگی دارد. در الگوی پیشنهادی:

- Google گواهی `MITM-DomainFronting` را نشان می‌دهد.
- صفحه کنترل YouTube و Gemini که به VPN فرستاده شده‌اند گواهی عمومی نشان می‌دهند.
- Cloudflare به‌عنوان دامنه کنترل، گواهی عمومی عادی نشان می‌دهد.

## ارتقا

ارتقای بسته، `/etc/config/xray-mitm` و کل پوشه `/etc/xray-mitm/` را حفظ می‌کند. نمونه تنظیمات جدید جای تنظیمات فعال، CA یا کلید خصوصی را نمی‌گیرد. بااین‌حال قبل از ارتقا از تنظیمات و کلید خصوصی یک نسخه پشتیبان محافظت‌شده تهیه کنید.

## حذف

قبل از حذف، سرویس را متوقف و اجرای خودکار آن را غیرفعال کنید. اگر اتصال PassWall2 را اعمال کرده‌اید، ابتدا از صفحه LuCI پروژه rollback را اجرا کنید. سپس CA عمومی را از trust store تمام کلاینت‌ها حذف کنید و کلید خصوصی باقی‌مانده روی روتر را محرمانه نگه دارید.

## نکات امنیتی

- فقط `mycert.crt` عمومی را روی کلاینت‌ها نصب کنید.
- `mycert.key` را فقط روی روتر و در نسخه پشتیبان رمزگذاری‌شده یا محافظت‌شده نگه دارید.
- نسخه پشتیبان OpenWrt می‌تواند کلید خصوصی CA را در خود داشته باشد.
- snapshot بازگشت PassWall2 می‌تواند مشخصات node و اطلاعات ورود پراکسی را در خود داشته باشد.
- فایل‌های پشتیبان روتر، کلیدها یا تنظیمات واقعی PassWall2 را در GitHub Issue یا Release قرار ندهید.

برای جزئیات معماری، build، وابستگی‌ها و آزمایش انتشار، [راهنمای انگلیسی](README.md) را ببینید.

این پروژه مستقل از Xray-core، OpenWrt، LuCI و PassWall2 است.

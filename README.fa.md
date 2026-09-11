# Xray MITM Domain Fronting برای OpenWrt

**نسخه:** `v0.4.2` · **راهنما:** [English](README.md) | فارسی · **پروژه:** [فهرست تغییرات](CHANGELOG.md) | [راهنمای مشارکت](CONTRIBUTING.md)

این پروژه سرویس مستقل Xray MITM-DomainFronting، داشبورد LuCI و مسیریابی اختیاری PassWall2 را برای روترهای رسمی OpenWrt 25.12 که از APK استفاده می‌کنند فراهم می‌کند.

برای بیشتر کاربران:

1. با یک دستور نصب یا به‌روزرسانی کنید.
2. در LuCI به **Services → MITM Domain Fronting** بروید.
3. در بخش **Basic** گزینه **Set up automatically** را انتخاب کنید.
4. گواهی عمومی را دانلود و مورد اعتماد کنید.
5. VPN موجود را انتخاب و مسیریابی پیشنهادی را بررسی کنید.
6. مسیریابی را اعمال و **Run check** را اجرا کنید.

> [!CAUTION]
> نرم‌افزار MITM می‌تواند ترافیک HTTPS دستگاه‌هایی را که به گواهی آن اعتماد دارند رمزگشایی کند. فقط در شبکه و دستگاه‌هایی استفاده کنید که مالک آن‌ها هستید یا اجازه مدیریتشان را دارید. فقط `mycert.crt` را روی کلاینت نصب کنید. `mycert.key` باید روی روتر و در نسخه‌های پشتیبان محافظت‌شده باقی بماند.

## نیازمندی‌ها

- OpenWrt رسمی 25.12.5 یا یکی از نسخه‌های نگهداری بعدی سری 25.12، همراه با `apk` و LuCI.
- دسترسی روتر به GitHub و GitHub Pages.
- PassWall2 برای مسیریابی خودکار؛ خود سرویس MITM به PassWall2 نیاز ندارد.
- یک پروفایل shunt فعال و یک VPN سالم در PassWall2 برای سرویس‌هایی که باید از VPN عبور کنند.

## سازگاری

- OpenWrt رسمی 25.12.x با بسته‌های APK: `xray-mitm` و `luci-app-xray-mitm`.
- سخت‌افزار آزمایش‌شده: ASUS TUF-AX4200. سخت‌افزارهای دیگر ممکن است کار کنند، اما در فهرست آزمایش‌شده نیستند.

## نصب یا به‌روزرسانی

همین دستور برای نصب اولیه و به‌روزرسانی‌های بعدی استفاده می‌شود. اگر آدرس روتر متفاوت است، `192.168.1.1` را تغییر دهید.

**MAC:**

```sh
ssh root@192.168.1.1 'wget -qO /tmp/install-xray-mitm.sh https://duuuude.github.io/xray-mitm-openwrt/install.sh && printf "%s  %s\n" "8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405" "/tmp/install-xray-mitm.sh" | sha256sum -c - && sh /tmp/install-xray-mitm.sh'
```

**WINDOWS PC (PowerShell):**

```powershell
ssh.exe root@192.168.1.1 'wget -qO /tmp/install-xray-mitm.sh https://duuuude.github.io/xray-mitm-openwrt/install.sh && printf "%s  %s\n" "8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405" "/tmp/install-xray-mitm.sh" | sha256sum -c - && sh /tmp/install-xray-mitm.sh'
```

اگر از قبل داخل SSH روتر هستید:

**ROUTER:**

```sh
wget -qO /tmp/install-xray-mitm.sh https://duuuude.github.io/xray-mitm-openwrt/install.sh && printf '%s  %s\n' '8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405' '/tmp/install-xray-mitm.sh' | sha256sum -c - && sh /tmp/install-xray-mitm.sh
```

نصب‌کننده نسخه OpenWrt، checksum نصب‌کننده و feed امضاشده را بررسی می‌کند، نسخه پشتیبان محافظت‌شده می‌سازد و فقط بسته‌های پروژه را نصب یا به‌روزرسانی می‌کند. PassWall2 نصب نمی‌شود، گواهی ساخته نمی‌شود، MITM روشن نمی‌شود و مسیریابی تغییر نمی‌کند.

SHA-256 ثابت نصب‌کننده این است: `8af96edc133c01a7e9d0a8f4673b7225c47322d73874c05a9c4a0133f3058405`.

بعد از پایان، LuCI را با **HTTPS** در مسیر **Services → MITM Domain Fronting** باز کنید.

## راه‌اندازی اولیه

این روند برای نصب تازه است. به‌روزرسانی تنظیمات، گواهی فعال، وضعیت سرویس و مسیریابی PassWall2 را حفظ می‌کند؛ فقط اگر LuCI چیزی را ناقص اعلام کرد راه‌اندازی را تکرار کنید.

### ۱. آماده‌سازی روتر

در **Basic → Setup** گزینه **Set up automatically** را انتخاب کنید.

این گزینه پیکربندی پیش‌فرض را در صورت نیاز آماده می‌کند، گواهی را در صورت نیاز می‌سازد و فعال می‌کند، MITM را روشن می‌کند و شروع خودکار بعد از راه‌اندازی مجدد را فعال می‌کند. پیکربندی و گواهی معتبر موجود را حفظ می‌کند و PassWall2 را نصب نمی‌کند.

### ۲. دانلود و اعتماد به گواهی عمومی

در **Basic → Setup** گزینه **Download public certificate** را انتخاب کنید. فقط `mycert.crt` را روی دستگاه‌هایی نصب کنید که باید از MITM استفاده کنند؛ کلید خصوصی روی روتر باقی می‌ماند.

- **macOS:** گواهی را باز کنید، به Keychain Access اضافه کنید و **Always Trust** را فعال کنید.
- **Windows:** گواهی را باز کنید، **Install Certificate** را بزنید و آن را در **Trusted Root Certification Authorities** قرار دهید.
- **Android:** تنظیمات Security را باز کنید، **Install a certificate** را انتخاب کنید و آن را به‌عنوان CA certificate نصب کنید.

نام منوها ممکن است در نسخه‌های مختلف سیستم‌عامل فرق کند. Firefox ممکن است از مخزن گواهی جداگانه استفاده کند. بعضی برنامه‌های native به گواهی نصب‌شده توسط کاربر اعتماد نمی‌کنند یا certificate pinning دارند؛ ابتدا مرورگر را آزمایش کنید.

### ۳. تنظیم مسیریابی پیشنهادی

اگر به مسیریابی PassWall2 نیاز ندارید، این مرحله را رد کنید. در غیر این صورت به **Basic → Routing** بروید و این موارد را انتخاب کنید:

- **Main routing profile** — پروفایل shunt که در PassWall2 فعال است.
- **Working VPN connection** — یک VPN موجود که از قبل کار می‌کند.

گزینه **Review selected routing** را بزنید، مقصدها را بررسی کنید و سپس **Apply recommended routing** را انتخاب کنید. مقصدهای MITM به سرویس روشن نیاز دارند؛ در صورت نیاز آن را از **Advanced → Service** روشن کنید. دستیار preview را بررسی و قوانین نامرتبط PassWall2 را حفظ می‌کند.

### ۴. بررسی عملکرد

به **Basic → Status** بروید و **Run check** را انتخاب کنید. این بررسی سرویس MITM روی روتر را آزمایش می‌کند و ثابت نمی‌کند که همه کلاینت‌ها به `mycert.crt` اعتماد دارند.

بعد از موفقیت، وب‌سایت‌ها را با مرورگر کلاینت آزمایش کنید. سایت MITM باید `MITM-DomainFronting` را به‌عنوان issuer نشان دهد؛ سایت VPN یا direct باید مرجع گواهی عمومی عادی خود را نشان دهد.

## مسیریابی پیشنهادی

مدل پیش‌فرض بر اساس هدف ترافیک است:

| ترافیک | مقصد | هدف |
| --- | --- | --- |
| سرویس‌های Google | MITM | استفاده از سرویس MITM محلی برای گروه انتخاب‌شده Google. |
| اپلیکیشن و API جمنای | VPN انتخاب‌شده | عبور ترافیک Gemini از VPN سالم. |
| وب‌سایت‌ها و IPهای ایران | Direct | عبور مستقیم ترافیک محلی انتخاب‌شده بدون VPN و MITM. |

گروه‌های اختیاری در **Basic → Routing** قرار دارند:

- **VPN Overrides** می‌تواند بررسی اتصال Android، ورود و کنترل‌های YouTube و ورود به حساب Google را شامل شود. `googlevideo.com` عمداً خارج است تا تحویل ویدئوی YouTube بتواند از MITM استفاده کند.
- **MITM-Compatible Services** می‌تواند گروه‌های Google، وب‌سایت‌های Meta و سایت‌های مبتنی بر Fastly را شامل شود. ابتدا Google را آزمایش کنید و قبل از اتکا به برنامه‌های native، Meta و Fastly را جداگانه آزمایش کنید.
- **Regional Direct Access** از گروه‌های دامنه و IP ایران استفاده می‌کند.

هر checkbox یک گروه سرویس را داخل یکی از این انتساب‌ها فعال می‌کند و قانون جداگانه نمی‌سازد. بیشتر کاربران می‌توانند انتخاب‌های پیشنهادی را بدون تغییر نگه دارند.

## به‌روزرسانی

همان دستور نصب را دوباره اجرا کنید. به‌روزرسانی تنظیمات، گواهی فعال، وضعیت سرویس و مسیریابی PassWall2 را حفظ می‌کند. سپس LuCI را reload کنید و کارت‌های وضعیت را ببینید؛ تا وقتی LuCI درخواست نکرده گواهی جدید نسازید یا راه‌اندازی اولیه را تکرار نکنید.

## مشکلات رایج

- **PassWall2 شناسایی نمی‌شود:** MITM می‌تواند اجرا شود، اما مسیریابی خودکار به PassWall2 نیاز دارد. آن را نصب و فعال کنید و LuCI را reload کنید.
- **VPN یا پروفایل مسیریابی پیدا نشد:** یک VPN یا پروفایل shunt سالم در PassWall2 بسازید و به **Basic → Routing** برگردید.
- **مسیرهای MITM کار نمی‌کنند:** در **Advanced → Service** روشن بودن MITM و اعتماد کلاینت به `mycert.crt` را بررسی کنید.
- **خطای certificate:** فقط `mycert.crt` فعلی را نصب کنید و هرگز `mycert.key` را کپی نکنید؛ وضعیت گواهی را در **Advanced → Certificates** بررسی کنید.
- **برنامه native کار نمی‌کند:** بعضی برنامه‌ها CA کاربر را نمی‌پذیرند، certificate pinning دارند یا خارج از گروه انتخاب‌شده کار می‌کنند. ابتدا مرورگر را بررسی کنید.

## بخش Advanced

بیشتر کاربران به مرجع فنی نیاز ندارند. جزئیات چرخه گواهی، کنترل دستی سرویس، مسیریابی سفارشی، rollback، recovery، SOCKS محلی و فرمان‌های CLI در این فایل‌هاست:

- [راهنمای پیشرفته](docs/ADVANCED.md)
- [امنیت](SECURITY.md)
- [عملیات feed امضاشده](docs/SIGNED_FEED.md)
- [آزمایش انتشار](docs/RELEASE_TESTING.md)
- [روند مشارکت و توسعه](CONTRIBUTING.md)

## حذف

اگر مسیریابی اعمال شده است، ابتدا آن را از LuCI rollback کنید. سپس روی روتر:

**ROUTER:**

```sh
/etc/init.d/xray-mitm stop
/etc/init.d/xray-mitm disable
apk del luci-app-xray-mitm xray-mitm
```

بعد از پایان استفاده، `mycert.crt` را از trust store کلاینت‌ها حذف کنید. نسخه‌های پشتیبان و `mycert.key` همچنان محرمانه هستند.

## انتساب

پیکربندی domain-fronting بسته از [patterniha/MITM-DomainFronting v23](https://github.com/patterniha/MITM-DomainFronting/tree/v23) گرفته شده و تحت مجوز GPL-3.0 است. Xray-core، OpenWrt، LuCI و PassWall2 پروژه‌های upstream جداگانه هستند. به [اعلان‌های third-party](THIRD_PARTY_NOTICES.md) مراجعه کنید.

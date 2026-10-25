# BUILD_GUIDE — كيف تبني APK بنفسك (دون أي استضافة مدفوعة)

## الحقائق أولًا (شفافية كاملة)

| البند | الحالة عند كتابة هذا الدليل |
|---|---|
| نواة بايثون (`python-runtime/`) | مُختبرة محليًا: 51/51 pytest ✓ |
| كود أندرويد (`app/`) | مكتمل — **لم يُبنَ محليًا** (بيئة التطوير بلا Android SDK) |
| بناء APK | يتم عبر **GitHub Actions** تلقائيًا عند أول push، أو محليًا كما أدناه |

## الطريق الأسهل: GitHub Actions (صفر أدوات على جهازك)

1. ارفع المستودع إلى GitHub (scripts/push_to_github.sh).
2. CI يبني `assembleDebug` ويرفع الأداة باسم `drs-bot-host-debug-apk`
   من صفحة Actions → آخر تشغيل ناجح → Artifacts.
3. حمّل APK وثبّته (اسمح بـ "تثبيت من مصادر غير معروفة").

## البناء المحلي

المتطلبات:
- JDK 17 (Temurin مثلاً)
- Gradle 8.9 (أو استخدم wrapper — انظر ملاحظة)
- Android SDK: platform 35 + build-tools (يثبّتها Android Studio تلقائيًا)
- **Python 3.12** على PATH — شرط Chaquopy 17 (يجب أن يطابق إصدار `version = "3.12"`)

الخطوات:

```bash
# 1) توليد الـ wrapper مرة واحدة (غير مضمّن في المستودع عمدًا)
gradle wrapper --gradle-version 8.9

# 2) بناء نسخة debug
./gradlew :app:assembleDebug

# الناتج:
# app/build/outputs/apk/debug/app-debug.apk
```

أو داخل Android Studio: افتح المجلد → انتظر أول Sync → Run ▶.

### ملاحظات مهمة

- **local.properties**: أنشئه محليًا (`sdk.dir=/path/to/android-sdk`) —
  مرفوع في .gitignore عمدًا ولا يُنسخ بين الأجهزة.
- **إضافة حزم pip للبوتات**: عدّل `app/build.gradle.kts`:

  ```kotlin
  chaquopy {
      defaultConfig {
          version = "3.12"
          pip { install("requests") }   // أي حزمة يحتاجها بوتك
      }
  }
  ```

  ثم أعد البناء. الواجهة تعرض تحذير «حزم ناقصة» للبوتات التي تطلب
  حزمة غير مدمجة (انظر BOT_SPEC §6).
- **أول بناء** ينزّل CPython للحزم من Maven Central — يحتاج إنترنت.

## توقيع نسخة release (اختياري)

```bash
keytool -genkey -v -keystore drs-release.jks -keyalg RSA -keysize 2048 \
        -validity 10000 -alias drs
# ثم أضف signingConfigs في app/build.gradle.kts أو استخدم Android Studio
./gradlew :app:assembleRelease
```

لا ترفع ملف `.jks` أبدًا إلى المستودع (مستبعد في .gitignore).

## تشغيل اختبارات النواة محليًا

```bash
cd python-runtime
python3 -m pytest tests -q      # يتطلب pytest >= 7 فقط، بلا أي تبعيات أخرى
```

## تجربة المضيف على سطح المكتب (بدون هاتف)

```bash
cd <repo root>
PYTHONPATH=python-runtime/src python3 -m drs_host.cli --data-dir /tmp/drs \
    run sample-bots/echo-bot --seconds 4
```

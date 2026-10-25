# ARCHITECTURE — بنية DRS Bot Host v1.0

## 1. الصورة الكبيرة

```
┌────────────────────────────────────────────────────────────────┐
│                     Android device (no server)                 │
│                                                                │
│  ┌────────────────────────── App process ───────────────────┐  │
│  │                                                          │  │
│  │  Kotlin + Jetpack Compose (UI)                           │  │
│  │  ├─ Dashboard / Bots / Import / BotDetail / Settings     │  │
│  │  ├─ ViewModels (StateFlow, poll كل 1.5s)                 │  │
│  │  └─ BotHostService (foreground, specialUse)              │  │
│  │        │ PyBridge (Chaquopy JNI)                         │  │
│  │        ▼                                                 │  │
│  │  ┌────────────────── embedded CPython 3.12 ───────────┐  │  │
│  │  │ drs_host.host_api  (facade — JSON-serializable)    │  │  │
│  │  │   └─ Supervisor                                    │  │  │
│  │  │        ├─ BotRunner thread  → bot A (main.py)      │  │  │
│  │  │        ├─ BotRunner thread  → bot B (main.py)      │  │  │
│  │  │        └─ restart timer     → BACKOFF policy       │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│         filesDir/botdata/bots/<id>/  (bot code + runtime.jsonl) │
└────────────────────────────────────────────────────────────────┘
```

لا يوجد أي سيرفر خارجي: الهاتف **هو** المضيف. الاستضافة مجانية
وخاصة بالكامل، والمشروع مفتوح المصدر (Apache-2.0).

## 2. الطبقات والمسؤوليات

### python-runtime/ (النواة المُختبرة — 51 اختبار pytest)
| الوحدة | المسؤولية |
|---|---|
| `manifest.py` | تحقق صارم من `bot.json` (spec v1) — يرفع أخطاء مقروءة، يرفض المفاتيح المجهولة |
| `importer.py` | استيراد ZIP/مجلد آمن: zip-slip، حدود حجم/عدد، قائمة امتدادات، تطبيع المجلد الجذري |
| `streams.py` | `sys.stdout` واعٍ بالخيوط: كل بوت يعزل `print()` داخل سجلاته |
| `logging.py` | RingBuffer في الذاكرة + JSONL دوّار على القرص (`logs/runtime.jsonl`) |
| `runner.py` | خيط لكل بوت: حقن السياق، تنفيذ `runpy`، تصنيف الخروج (COMPLETED/STOPPED/FAILED + traceback) |
| `supervisor.py` | آلة حالات + سياسات إعادة تشغيل مع تراجع أسّي + اكتشاف البوتات المثبتة |
| `host_api.py` | واجهة JSON-serializable يستهلكها Kotlin عبر Chaquopy وCLI عبر سطح المكتب |
| `cli.py` | تحقق ميداني على الحاسوب: `info/list/import/run/stop` |

### app/ (أندرويد — يُبنى في CI)
| الوحدة | المسؤولية |
|---|---|
| `PyBridge` | تشغيل CPython مرة واحدة + `configure(filesDir/botdata)` + جسر JSON |
| `BotRepository` | كل نداءات host_api عبر `json.dumps` → `org.json` (سطح JNI ضيق وآمن) |
| `BotHostService` | خدمة أمامية `specialUse` تُبقي العملية حية + WakeLock اختياري + إشعار بحالة البوتات |
| `BootReceiver` | إقلاع اختياري بحسب إعداد المستخدم |
| `SettingsStore` | DataStore: تشغيل عند الإقلاع، auto_start للبوتات، إبقاء CPU مستيقظًا |
| الشاشات | Compose: زجاج داكن (`GlassCard`/`GlowBackground`)، حالة حية، سجلات مباشرة بتلقيم سفلي |

## 3. تدفق الاستيراد

```
SAF picker (ZIP أو مجلد)
  → نسخ إلى cache (SafIo)
  → host_api.import_zip/import_folder
      → peek: تحقق من bot.json قبل أي فك
      → حارس overwrite (يرفض لو البوت يعمل)
      → فك آمن + كتابة بيان معياري
  → SupervisedBot جديد في الذاكرة
  → UI تنقل لشاشة البوت
```

## 4. تدفق التشغيل والإيقاف

```
start_bot(id)
  → فحص الحالة + min_python
  → BotRunner thread: حقن ctx + تسجيل stdout + runpy(main.py)
  → RUNNING
خروج البوت:
  → _on_exit: حسب الخروج والسياسة
      stop_requested → STOPPED
      FAILED + on_failure/always → BACKOFF (تأخير أسّي) → restarts+1 → STARTING
      COMPLETED + always → BACKOFF → إعادة
      غير ذلك → COMPLETED / FAILED نهائي
stop_bot(id):
  → stop_event.set() + STOPPING + إلغاء أي BACKOFF مجدول
  → join(8s) → STOPPED (أو بقاء STOPPING مع تحذير إن كان البوت معلّقًا)
```

## 5. حدود التصميم (قرارات صريحة)

- **خيوط لا عمليات**: Chaquopy = مفسر واحد لكل عملية؛ الفصل عبر خيوط مع
  عزل stdout. العزل الكامل بعمليات يتطلب مسار Termux/ملفات ثنائية — مؤجل
  عن قصد للحفاظ على APK بسيط.
- **pip عند البناء**: الحزم الخارجية تُدمج في APK (انظر BOT_SPEC §6).
- **specialUse**: `dataSync` له سقف 6 ساعات؛ التطبيق مخصص للبناء الذاتي
  وليس لمتجر Play، لذا specialUse هو النوع الصادق.
- **Polling لا callbacks**: الواجهة تستعلم كل 1.5s بدل callback عبر JNI —
  أبسط وأكثر متانة (حجم السجل ≤ 400 سجل في الذاكرة للعرض).
- **بدون Room**: مصدر الحقيقة الوحيد هو مخزن بايثون (`botdata/bots/`) —
  طبقة بيانات واحدة لا طبقتان يمكن أن تختلفا.
- **Gradle بدون wrapper في v1.0**: CI يثبت Gradle 8.11.1 صراحة؛ محليًا
  `gradle wrapper --gradle-version 8.11.1` (موثق في BUILD_GUIDE).

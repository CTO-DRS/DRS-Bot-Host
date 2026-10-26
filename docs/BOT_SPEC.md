# BOT_SPEC — مواصفة بوت DRS Bot Host (spec_version 1)

> Language: العربية (Arabic) — technical identifiers are kept in English.

هذا المستند هو **العقد الكامل** بين بوتك وبين المضيف. أي بوت بايثون يلتزم به
يعمل داخل التطبيق دون أي تعديل.

## 1. بنية مجلد البوت

```
my-bot/
├── bot.json          # البيان (إلزامي) — في جذر المجلد
├── main.py           # نقطة الدخول (أو ما تشير إليه entrypoint)
└── ...               # ملفات مساندة بالامتدادات المسموحة
```

الامتدادات المسموحة داخل الحزمة:
`py, json, txt, md, csv, ini, cfg, yaml, yml, toml`

الحدود القصوى: 25 MB للأرشيف المضغوط، 100 MB بعد الفك، 500 ملف.
حزمة ZIP يمكن أن تكون إما بجذر مباشر (`bot.json` في أعلى الأرشيف) أو داخل
مجلد واحد (`my-bot/bot.json`) — كلاهما يُطبعَّن تلقائيًا.

## 2. مخطط bot.json

| الحقل | النوع | إلزامي | القيمة الافتراضية | الوصف |
|---|---|---|---|---|
| `id` | string | نعم | — | معرّف فريد: أحرف صغيرة/أرقام/`-`/`_`، 2–64 خانة |
| `name` | string | نعم | — | اسم العرض |
| `version` | string | نعم | — | إصدار دلالي `1.0.0` |
| `entrypoint` | string | نعم | — | مسار نسبي لملف `.py` داخل المجلد |
| `language` | string | لا | `python` | اللغات المدعومة في v1.0: `python` فقط |
| `min_python` | string | لا | `null` | مثل `3.10` — يرفض التشغيل لو كانت بيئة المضيف أقدم |
| `author` | string | لا | `""` | — |
| `description` | string | لا | `""` | — |
| `requirements` | list[string] | لا | `[]` | أسماء حزم PyPI (انظر §6) |
| `config` | object | لا | `{}` | إعدادات حرة يقرأها البوت عبر `ctx.config` (قابلة للتعديل من التطبيق منذ v1.2) |
| `restart` | object | لا | انظر أدناه | سياسة إعادة التشغيل |
| `auto_start` | bool | لا | `false` | يبدأ تلقائيًا مع خدمة الاستضافة إن سمح الإعداد |
| `schedule` | object | لا | `null` | جدولة تشغيل تشبه cron (انظر أدناه — جديدة في v1.2) |
| `health` | object | لا | `null` | فحوص صحة دورية مع استرجاع تلقائي (انظر أدناه — جديد في v1.6) |
| `isolation` | string | لا | `"thread"` | نمط العزل: `"thread"` (افتراضي) أو `"process"` — عملية بايثون منفصلة مع إيقاف قسري حقيقي (جديد في v1.3؛ على الأندرويد داخل Chaquopy يعود للخيوط تلقائيًا) |
| `spec_version` | int | لا | `1` | إصدار المواصفة — يجب أن يكون 1 |

**restart** الافتراضي:

```json
{
  "policy": "on_failure",      // never | on_failure | always
  "max_restarts": 5,
  "backoff_seconds": 2.0,
  "backoff_multiplier": 2.0,
  "max_backoff_seconds": 60.0
}
```

- `never`: أي خروج يُنهي البوت نهائيًا.
- `on_failure`: يُعاد التشغيل فقط عند الانهيار بخطأ (أو `SystemExit != 0`).
- `always`: يُعاد التشغيل حتى بعد الخروج النظيف (بوتات الخدمات المستمرة).

**schedule** (جديد في v1.2) — جدولة تشغيل cron-like:

```json
{
  "kind": "interval",          // interval | daily
  "interval_seconds": 3600,    // إلزامي لـ interval: كل كم يبدأ تشغيل جديد
  "run_seconds": 300,          // اختياري: يُوقف التشغيل بعد هذه المدة
  "enabled": true              // اختياري (افتراضي true) — يُدار من التطبيق
}
```

```json
{
  "kind": "daily",
  "time": "09:00",              // إلزامي لـ daily: بتوقيت الجهاز المحلي
  "duration_seconds": 3600,     // اختياري: مدة بقاء النافذة مفتوحة
  "enabled": true
}
```

- المُجدوِل يعمل على **حواف النوافذ** فقط: بوت أوقفته يدويًا لن يُعاد
  تشغيله قسرًا قبل النافذة التالية.
- يمكن تمكين/تعطيل الجدولة أثناء التشغيل من شاشة تفاصيل البوت أو عبر
  `host_api.set_schedule_enabled(bot_id, true|false)` — ويُحفظ في `bot.json`.
- حالة `RUNNING` داخل نافذة تظهر "النافذة التالية" في الواجهة.
- مفاتيح غير معروفة أو قيم خارج المدى **ترفض** بصرامة مثل باقي البيان.

**health** (جديد في v1.6) — فحوص صحة دورية أثناء عمل البوت مع استرجاع تلقائي:

```json
{
  "kind": "http",               // http | command
  "url": "http://127.0.0.1:8080/health",  // إلزامي لـ http
  "expect_status": 200,         // اختياري: رمز HTTP المقبول (افتراضي 200)
  "interval_seconds": 30,       // 5–86400 (افتراضي 30)
  "timeout_seconds": 5,         // 1–60 (افتراضي 5)
  "failure_threshold": 3,       // 1–100 إخفاق متتالي ⇒ غير سليم
  "success_threshold": 1,       // 1–100 نجاح متتالٍ ⇒ سليم مجددًا
  "recover": "restart",         // none | restart | force_stop
  "enabled": true
}
```

```json
{
  "kind": "command",
  "script": "health.py",        // إلزامي لـ command: مسار نسبي لملف .py داخل مجلد البوت
  "recover": "force_stop"
}
```

- **http**: طلب GET دوري؛ النجاح عندما يساوي رمز الاستجابة `expect_status`.
- **command**: استيراد السكربت واستدعاء `check()` — تُعيد `True`/`False`
  أو `(bool, detail)`. يعمل داخل نفس المفسّر (متوافق مع Chaquopy)؛ لا
  shell ولا أوامر عشوائية. `check()` التي لا تنتهي تُحسب "مهلة انتهت"
  بعد `timeout_seconds`.
- تُفحص فقط البوتات في حالة `RUNNING` (وغير المفصولة).
- بعد بلوغ `failure_threshold` يُطبّق `recover`: إعادة تشغيل رشيقة، أو
  `force_stop` ثم بدء جديد، أو لا شيء (يبقى البوت موسومًا "غير سليم").
- يدويًا: `host_api.probe_health(bot_id)` (تشخيص بلا استرجاع)،
  `set_health_enabled(bot_id, true|false)` (يُحفظ في `bot.json`)،
  أو أمر CLI `health` / `health-probe`.
- مفاتيح غير معروفة أو قيم خارج المدى **ترفض** بصرامة.

المفاتيح غير المعروفة **ترفض** بصرامة (حماية من الأخطاء المطبعية).

## 3. عقد التشغيل (مهم جدًا)

يعمل البوت داخل **خيط (thread)** في نفس مفسر بايثون الخاص بالتطبيق
(Chaquopy). خيوط بايثون لا يمكن قتلها قسرًا، لذلك:

1. البوت يجب أن يكون **تعاونيًا**: يفحص `ctx.should_stop` أو يستخدم
   `ctx.sleep_or_stop()` في كل دورة.
2. البوت الذي يتجاهل الإيقاف يبقى في حالة `STOPPING` مع تحذير. منذ v1.2
   يوفر التطبيق زر **إيقاف قسري** (`force_stop`) الذي **يفصل** الخيط
   العنيد عن الإشراف ويعلّم البوت `FORCE_STOPPED` — الخيط قد يستمر
   العمل حتى موت العملية (لا يمكن قتل خيوط بايثون)، لكنه لم يعد يؤثر
   على حالة البوت أو سجلاته، وعلى أندرويد يبقى قتل العملية كاملة
   (من النظام أو إعادة تشغيل الخدمة) هو الإيقاف الحقيقي النهائي.
3. `main.py` يُنفَّذ بـ `__name__ == "__main__"`، فتعمل الأنماط المعتادة
   (`if __name__ == "__main__": main()`) والسكربتات التنفيذية المباشرة.

## 4. SDK البوت

```python
from drs_host.sdk import get_context

ctx = get_context()
```

| العنصر | النوع | الوصف |
|---|---|---|
| `ctx.bot_id` | str | معرّف البوت |
| `ctx.name` | str | اسمه |
| `ctx.config` | dict | نسخة من حقل `config` في البيان |
| `ctx.logger` | BotLogger | `.debug/.info/.warning/.error(msg)` — سجلات منظمة لكل بوت |
| `ctx.stop_event` | threading.Event | يُفعَّل عند طلب الإيقاف |
| `ctx.should_stop` | bool | اختصار لـ `stop_event.is_set()` |
| `ctx.sleep_or_stop(seconds)` | bool | ينام حتى `seconds` ويعيد True لو طُلب الإيقاف أثناء النوم |
| `ctx.set_progress(value, total, label)` | — | يظهر شريط تقدم في واجهة التطبيق |
| `get_context()` | BotContext \| None | يعيد None خارج خيط بوت (لتشغيل standalone) |

خارج المضيف يمكن للبوت أن يعمل مستقلًا: `get_context()` يعيد `None` —
اكتب مسارًا بديلًا بسيطًا كما في بوت `echo-bot` النموذجي.

## 5. مثال كامل

```python
# main.py
from drs_host.sdk import get_context

ctx = get_context()
interval = float(ctx.config.get("interval_seconds", 5.0))

ctx.logger.info("started")
while not ctx.should_stop:
    ctx.logger.info("doing work")
    ctx.set_progress(value=1, total=1, label="cycle")
    ctx.sleep_or_stop(interval)
ctx.logger.info("stopped")
```

```json
{
  "id": "worker",
  "name": "Worker Bot",
  "version": "1.0.0",
  "entrypoint": "main.py",
  "config": {"interval_seconds": 5.0},
  "restart": {"policy": "always", "max_restarts": 10},
  "auto_start": true
}
```

## 6. قيود v1.2 المعروفة (بصراحة)

1. **حزم pip تُثبَّت وقت بناء APK وليس وقت تشغيل البوت.** Chaquopy يدمج
   الحزم داخل APK أثناء البناء. بوت يستخدم مكتبة خارجية (مثل `requests`)
   يتطلب إضافتها إلى `app/build.gradle.kts` داخل
   `chaquopy.defaultConfig.pip { install("requests") }` ثم إعادة بناء APK.
   منذ v1.2: سياسة **المتطلبات** (off/warn/enforce) تفحص عند التشغيل —
   `enforce` يمنع بدء بوت يحتاج حزمًا غير مدمجة، و`warn` يسجّل تحذيرًا في
   سجل البوت نفسه، والفحص يجمع بين قائمة الحزم المدمجة
   (`set_available_packages`) و`find_spec` على المفسّر الحي.
2. **لا فصل بعمليات منفصلة (subprocess)** — الفصل بين البوتات بخيوط +
   التقاط stdout لكل خيط + `cpu_seconds` لكل خيط منذ v1.2. عزل كامل
   بعمليات مع kill حقيقي = خارطة طريق.
3. **الإيقاف تعاوني أصلًا** (انظر §3) — `force_stop` منذ v1.2 يفصل
   الخيط العنيد لكنه لا يقتله فعلًا.
4. `os.fork` و`signal` ووحدات تتطلب TTY غير مدعومة داخل أندرويد.

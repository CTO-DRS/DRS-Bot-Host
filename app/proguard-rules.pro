# Keep Chaquopy API surface used reflectively
-keep class com.chaquo.python.** { *; }

# Keep our facade entry points referenced from Python/Kotlin bridge
-keep class com.drsbot.host.python.PyBridge { *; }

# Compose / Kotlin coroutines ship their own consumer rules.

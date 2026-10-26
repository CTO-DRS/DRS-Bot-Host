package com.drsbot.host.util

import androidx.core.os.LocaleListCompat

/**
 * Resolves the Wi-Fi status-page language (v1.9) from the persisted UI
 * language preference.
 *
 * The browser dashboard is rendered by the Python runtime, which cannot see
 * the Android locale, so the app resolves the setting once and passes the
 * result through `web_status_start(language=...)`:
 * - "ar"  -> Arabic right-to-left dashboard
 * - "en"  -> English dashboard
 * - "system" -> follows the device locale (Arabic when the primary locale
 *    is Arabic, English otherwise)
 */
object PageLanguage {
    fun resolve(settingsLanguage: String): String = when (settingsLanguage) {
        "ar" -> "ar"
        "en" -> "en"
        else ->
            if (LocaleListCompat.getAdjustedDefault().get(0)?.language == "ar") {
                "ar"
            } else {
                "en"
            }
    }
}

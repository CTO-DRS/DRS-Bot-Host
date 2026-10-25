package com.drsbot.host.util

import android.content.Context
import android.net.Uri
import androidx.documentfile.provider.DocumentFile
import java.io.File

/**
 * SAF (Storage Access Framework) copy helpers: both import paths materialize
 * the user's selection into the app cache, then the verified python importer
 * performs ALL validation and copying into the bot storage.
 */
object SafIo {

    /** Copy a content:// zip into the cache; returns the local file. */
    fun copyUriToCache(context: Context, uri: Uri, displayName: String): File {
        val cacheDir = File(context.cacheDir, "imports").apply { mkdirs() }
        val target = File(cacheDir, displayName.ifBlank { "import-${System.currentTimeMillis()}.zip" })
        context.contentResolver.openInputStream(uri)?.use { input ->
            target.outputStream().use { output ->
                input.copyTo(output, bufferSize = 64 * 1024)
            }
        } ?: throw IllegalStateException("Cannot open $uri")
        return target
    }

    /**
     * Recursively copy a SAF document tree into a cache directory.
     * Only regular files are copied; names are sanitized defensively.
     */
    fun copyTreeToCache(context: Context, treeUri: Uri, destName: String): File {
        val root = DocumentFile.fromTreeUri(context, treeUri)
            ?: throw IllegalStateException("Cannot open tree $treeUri")
        val destRoot = File(context.cacheDir, "imports/$destName").apply { mkdirs() }
        copyTreeRecursive(context, root, destRoot)
        return destRoot
    }

    private fun copyTreeRecursive(context: Context, source: DocumentFile, target: File) {
        source.listFiles().forEach { entry ->
            val safeName = entry.name?.replace(Regex("[\\\\/:*?\"<>|]"), "_") ?: return@forEach
            if (entry.isDirectory) {
                copyTreeRecursive(context, entry, File(target, safeName).apply { mkdirs() })
            } else if (entry.isFile) {
                val out = File(target, safeName)
                context.contentResolver.openInputStream(entry.uri)?.use { input ->
                    out.outputStream().use { output ->
                        input.copyTo(output, bufferSize = 64 * 1024)
                    }
                }
            }
        }
    }

    /** Clear cached import material (called after each import attempt). */
    fun clearCache(context: Context) {
        File(context.cacheDir, "imports").deleteRecursively()
    }
}

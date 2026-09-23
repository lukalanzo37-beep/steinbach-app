/*
 * SecureMessengerDatabase.kt
 *
 * Room-Datenbank, deren zugrundeliegende SQLite-Datei per SQLCipher
 * (AES-256, transparente Seitenverschluesselung) verschluesselt ist. Das
 * Schema entspricht db/schema.sql.
 *
 * Der SQLCipher-Passphrase wird NIE hartcodiert und NIE im Klartext auf
 * Disk abgelegt -- er wird per Envelope Encryption aus einem
 * Keystore-gebundenen Schluessel abgeleitet, demselben Muster wie beim
 * Identitaets-Private-Key (siehe client/android/SecureKeyStorage.kt).
 *
 * Gradle: implementation "net.zetetic:android-database-sqlcipher:4.5.4"
 *         implementation "androidx.sqlite:sqlite:2.4.0"
 */

package com.example.securemessenger.db

import android.content.Context
import androidx.room.Database
import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.room.Room
import androidx.room.RoomDatabase
import com.example.securemessenger.crypto.SecureKeyStorage
import net.sqlcipher.database.SQLiteDatabase
import net.sqlcipher.database.SupportFactory
import java.security.SecureRandom

@Entity(tableName = "contacts")
data class ContactEntity(
    @PrimaryKey val anonId: String,
    val publicKey: ByteArray,
    val nickname: String?,
    val verificationLevel: Int,
    val addedAt: Long
)

@Entity(tableName = "conversations")
data class ConversationEntity(
    @PrimaryKey val id: String,
    val contactAnonId: String,
    val lastMessageAt: Long?,
    val isArchived: Boolean
)

@Entity(tableName = "messages")
data class MessageEntity(
    @PrimaryKey val id: String,
    val conversationId: String,
    val direction: Int, // 0 = eingehend, 1 = ausgehend
    val body: String?,
    val sentAt: Long?,
    val receivedAt: Long?,
    val deliveryState: Int, // 0..4, siehe schema.sql
    val senderPublicKey: ByteArray
)

@Database(
    entities = [ContactEntity::class, ConversationEntity::class, MessageEntity::class],
    version = 1,
    exportSchema = true
)
abstract class SecureMessengerDatabase : RoomDatabase() {
    abstract fun contactDao(): ContactDao
    abstract fun messageDao(): MessageDao
}

/**
 * Erzeugt (oder oeffnet) die verschluesselte Room-Datenbank. Die Passphrase
 * kommt ausschliesslich aus [DbKeyProvider] und wird nach Gebrauch aktiv
 * ueberschrieben.
 */
object DatabaseProvider {

    fun build(context: Context, keyStorage: SecureKeyStorage): SecureMessengerDatabase {
        SQLiteDatabase.loadLibs(context)

        val passphrase = DbKeyProvider.getOrCreatePassphrase(keyStorage)
        try {
            val factory = SupportFactory(passphrase)
            return Room.databaseBuilder(
                context,
                SecureMessengerDatabase::class.java,
                "messenger.db"
            )
                .openHelperFactory(factory)
                .build()
        } finally {
            passphrase.fill(0)
        }
    }
}

/**
 * Verwaltet den 256-Bit-Zufallsschluessel, der als SQLCipher-Passphrase
 * dient. Der Schluessel selbst wird -- genau wie der Identitaets-Private-Key
 * -- per Envelope Encryption ueber den Android Keystore geschuetzt
 * abgelegt, niemals im Klartext.
 */
object DbKeyProvider {

    private val secureRandom = SecureRandom()

    fun getOrCreatePassphrase(keyStorage: SecureKeyStorage): ByteArray {
        return try {
            keyStorage.unwrapDatabaseKey()
        } catch (_: Exception) {
            val newKey = ByteArray(32)
            secureRandom.nextBytes(newKey)
            keyStorage.wrapAndStoreDatabaseKey(newKey.copyOf())
            newKey
        }
    }
}

/*
 * Ergaenzung zu SecureKeyStorage (client/android/SecureKeyStorage.kt):
 * Dort existieren bereits `wrapAndStorePrivateKey`/`unwrapPrivateKey` fuer
 * den Identitaetsschluessel. Fuer den DB-Schluessel wird analog verfahren,
 * mit einem eigenen Keystore-Alias/Prefs-Eintrag (z. B. "db_key_wrapper"),
 * damit ein Leak des einen Schluessels nicht automatisch den anderen
 * kompromittiert. Der Kuerze halber hier nicht erneut ausgeschrieben.
 */

package io.github.db9979.spark

import android.app.Activity
import android.hardware.biometrics.BiometricManager
import android.hardware.biometrics.BiometricPrompt
import android.os.Build
import android.os.CancellationSignal

/**
 * "Android: Fingerabdruck für Admins" (admin switch chat.android_lock): when the login in the app has admin rights,
 * the app asks for the phone's fingerprint, face or screen lock before it shows the Spark, at the start and after
 * AFTER in the background (like Face ID before "Spark verwalten" in the iPhone app). Android checks it; the app
 * learns only yes or no. A phone without any screen lock has nothing to check: the app says so and opens.
 */
object Lock {
    const val AFTER = 5 * 60 * 1000L

    fun needed(s: Store, now: Long = System.currentTimeMillis()) = s.lock && s.admin && now - s.leftAt > AFTER

    /** Android's own prompt; [ok] after the right finger, face or code, [no] when the person cancels. */
    fun ask(a: Activity, ok: () -> Unit, no: (String) -> Unit) {
        val b = BiometricPrompt.Builder(a).setTitle("Spark entsperren")
            .setSubtitle("Du bist in der App mit Admin-Rechten angemeldet.")
        if (Build.VERSION.SDK_INT >= 30) {
            b.setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG or BiometricManager.Authenticators.DEVICE_CREDENTIAL)
        } else {
            @Suppress("DEPRECATION")
            b.setDeviceCredentialAllowed(true)
        }
        try {
            b.build().authenticate(CancellationSignal(), a.mainExecutor, object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) = ok()

                override fun onAuthenticationError(code: Int, msg: CharSequence) {
                    when (code) {
                        // nothing to check on this phone: no screen lock at all (a sensor that is busy stays locked)
                        BiometricPrompt.BIOMETRIC_ERROR_NO_DEVICE_CREDENTIAL -> {
                            android.widget.Toast.makeText(a, "Das Handy hat keine Displaysperre: der Schutz greift erst mit einer.", android.widget.Toast.LENGTH_LONG).show()
                            ok()
                        }
                        else -> no("Gesperrt. Antippen zum Entsperren.")
                    }
                }
            })
        } catch (_: Exception) {
            no("Entsperren geht gerade nicht. Antippen für einen neuen Versuch.")
        }
    }
}

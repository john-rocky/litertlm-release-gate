package dev.relgate.litertlm

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.google.ai.edge.litertlm.Backend
import com.google.ai.edge.litertlm.Engine
import com.google.ai.edge.litertlm.EngineConfig
import java.io.File
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Release-artifact gate: the published litertlm-android AAR must init and finish
 * ONE text generate on a real device.
 *
 * The interesting part is the END of the turn: Conversation's JNI callback closes
 * the flow's channel in onDone, which is where 0.16.1 throws
 * NoSuchMethodError SendChannel.close$default (#3334) and where 0.16.0 never
 * called back at all, hanging collect() forever (#3266). A timeout maps to
 * #3266-shape, a NoSuchMethodError crash to #3334-shape; both leave their stack
 * in the instrumentation output for maven_check.sh to classify.
 */
@RunWith(AndroidJUnit4::class)
class GateTest {
    @Test
    fun initAndOneGenerate() {
        val model = File("/data/local/tmp/relgate/canary.litertlm")
        assertTrue("canary model not pushed to ${model.path}", model.exists())

        val engine = Engine(EngineConfig(modelPath = model.absolutePath, backend = Backend.CPU()))
        engine.use {
            it.initialize()
            Log.i(TAG, "engine initialized")
            val sb = StringBuilder()
            runBlocking {
                withTimeout(240_000) {
                    it.createConversation().use { conversation ->
                        conversation.sendMessageAsync(PROMPT).collect { chunk -> sb.append(chunk) }
                    }
                }
            }
            Log.i(TAG, "ANSWER: $sb")
            assertTrue("collect completed but response is empty", sb.isNotBlank())
        }
    }

    companion object {
        private const val TAG = "RELGATE"
        private const val PROMPT = "What is 17 + 25? Answer briefly."
    }
}

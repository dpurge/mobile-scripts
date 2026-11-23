package local.mobilescripts

/**
 * Counts failures in a row and says when [limit] is reached; a success starts the count again.
 * Pure (no Android classes), so it is easy to unit test.
 */
class ConsecutiveFailures(private val limit: Int) {
    private var count = 0

    fun recordSuccess() {
        count = 0
    }

    /** Returns true once [limit] failures happened in a row. */
    fun recordFailure(): Boolean {
        count++
        return count >= limit
    }
}

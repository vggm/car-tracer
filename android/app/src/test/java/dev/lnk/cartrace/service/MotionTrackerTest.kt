package dev.lnk.cartrace.service

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MotionTrackerTest {
    private var now = 1_000_000L
    private val tracker = MotionTracker { now }

    @Test fun noFixIsNotMoving() = assertFalse(tracker.isMoving())

    @Test fun fastFreshFixIsMoving() {
        tracker.onFix(10.0)
        now += 5_000
        assertTrue(tracker.isMoving())
    }

    @Test fun slowFixIsNotMoving() {
        tracker.onFix(0.5)
        assertFalse(tracker.isMoving())
    }

    @Test fun fastButStaleFixIsNotMoving() {
        tracker.onFix(10.0)
        now += 15_000
        assertFalse(tracker.isMoving())
    }

    @Test fun justUnderFreshWindowIsMoving() {
        tracker.onFix(10.0)
        now += 14_999
        assertTrue(tracker.isMoving())
    }

    @Test fun nullSpeedIsNotMoving() {
        tracker.onFix(null)
        assertFalse(tracker.isMoving())
    }

    @Test fun nullSpeedAfterFastFixStopsMoving() {
        tracker.onFix(10.0)
        tracker.onFix(null)
        assertFalse(tracker.isMoving())
    }

    @Test fun fiveKmhBoundaryCounts() {
        tracker.onFix(MotionTracker.MOVING_MIN_MPS)
        assertTrue(tracker.isMoving())
        tracker.onFix(MotionTracker.MOVING_MIN_MPS - 0.01)
        assertFalse(tracker.isMoving())
    }
}

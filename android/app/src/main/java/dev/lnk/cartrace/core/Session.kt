package dev.lnk.cartrace.core

import java.util.UUID
import java.util.concurrent.atomic.AtomicLong

class Session(val id: String = UUID.randomUUID().toString()) {
    private val seq = AtomicLong(0)
    fun nextSeq(): Long = seq.getAndIncrement()
}

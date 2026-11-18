package dev.lnk.cartrace.obd

enum class Pid(val cmd: String, val key: String) {
    RPM("010C", "rpm"),
    SPEED("010D", "speed_kmh"),
    COOLANT("0105", "coolant_c"),
    INTAKE("010B", "intake_kpa"),
    LOAD("0104", "load_pct"),
    THROTTLE("0111", "throttle_pct"),
    FUEL_RATE("015E", "fuel_rate_lph"),
}

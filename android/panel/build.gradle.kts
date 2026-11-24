import java.net.URI
import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
}

// Release signing: optional, read from outside the repo (same as :app).
val signingProps = Properties().apply {
    val f = File(System.getProperty("user.home"), ".android-keys/car-trace.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

// The panel URL is private (never committed): it lives in android/local.properties.
val localProps = Properties().apply {
    val f = rootProject.file("local.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}
val panelUrlProp: String? = localProps.getProperty("panel.url")?.trim()?.takeIf { it.isNotEmpty() }
val debugFallbackUrl = "http://10.0.2.2:8090/"

fun panelUrlFor(release: Boolean): String =
    panelUrlProp ?: if (release) {
        throw GradleException(
            "panel.url is missing in android/local.properties. " +
                "Add e.g. panel.url=http://<tailscale-host>:8090/ to build the release APK."
        )
    } else debugFallbackUrl

/** Generates res/xml/network_security_config.xml with cleartext allowed only for the panel host. */
abstract class GenerateNetworkSecurityConfig : DefaultTask() {
    @get:Input
    abstract val panelUrl: Property<String>

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @TaskAction
    fun generate() {
        val host = URI(panelUrl.get()).host
            ?: throw GradleException("panel.url has no host: ${panelUrl.get()}")
        val dir = outputDir.get().asFile.resolve("xml").apply { mkdirs() }
        dir.resolve("network_security_config.xml").writeText(
            """<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="false" />
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="false">$host</domain>
    </domain-config>
</network-security-config>
"""
        )
    }
}

android {
    namespace = "dev.lnk.cartrace.panel"
    compileSdk = 37

    defaultConfig {
        applicationId = "dev.lnk.cartrace.panel"
        minSdk = 33
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
    }

    signingConfigs {
        if (signingProps.containsKey("storeFile")) {
            create("release") {
                storeFile = file(signingProps.getProperty("storeFile"))
                storePassword = signingProps.getProperty("storePassword")
                keyAlias = signingProps.getProperty("keyAlias")
                keyPassword = signingProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        debug {
            buildConfigField("String", "PANEL_URL", "\"${panelUrlFor(false)}\"")
        }
        release {
            isMinifyEnabled = false
            buildConfigField("String", "PANEL_URL", "\"${panelUrlFor(true)}\"")
            signingConfigs.findByName("release")?.let { signingConfig = it }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = true
    }
}

androidComponents {
    onVariants { variant ->
        val isRelease = variant.buildType == "release"
        val task = tasks.register<GenerateNetworkSecurityConfig>(
            "generate${variant.name.replaceFirstChar { it.uppercase() }}NetworkSecurityConfig"
        ) {
            // Resolved lazily so tasks of other variants don't fail the configuration.
            panelUrl.set(provider { panelUrlFor(isRelease) })
        }
        variant.sources.res?.addGeneratedSourceDirectory(task, GenerateNetworkSecurityConfig::outputDir)
    }
}

dependencies {
    implementation(libs.androidx.activity)

    testImplementation(libs.junit)
}

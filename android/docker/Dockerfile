# Own build image: JDK + Android command-line tools + SDK 34 + Gradle. Versions and their sources
# are recorded in android/README.md.
FROM eclipse-temurin:21-jdk

ARG CMDLINE_TOOLS=16111833
ARG BUILD_TOOLS=36.0.0
ARG GRADLE=9.9.2

ENV ANDROID_HOME=/opt/android-sdk \
    GRADLE_HOME=/opt/gradle
ENV PATH="${GRADLE_HOME}/bin:${ANDROID_HOME}/cmdline-tools/latest/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends unzip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL -o /tmp/cmdline.zip "https://dl.google.com/android/repository/commandlinetools-linux-${CMDLINE_TOOLS}_latest.zip" \
    && mkdir -p "${ANDROID_HOME}/cmdline-tools" \
    && unzip -q /tmp/cmdline.zip -d "${ANDROID_HOME}/cmdline-tools" \
    && mv "${ANDROID_HOME}/cmdline-tools/cmdline-tools" "${ANDROID_HOME}/cmdline-tools/latest" \
    && rm /tmp/cmdline.zip

# Gradle's download redirects to github.com, whose TLS certificate is not trusted inside the
# container on this network (self-signed chain), so build_apk.py fetches and verifies the zip
# on the host and the build context contains only that file.
COPY gradle-${GRADLE}-bin.zip /tmp/gradle.zip
RUN unzip -q /tmp/gradle.zip -d /opt \
    && mv "/opt/gradle-${GRADLE}" "${GRADLE_HOME}" \
    && rm /tmp/gradle.zip

# `yes` closes the pipe when sdkmanager exits, so pipefail is not used here.
RUN yes | sdkmanager --licenses > /dev/null \
    && sdkmanager "platforms;android-34" "build-tools;${BUILD_TOOLS}"

WORKDIR /workspace

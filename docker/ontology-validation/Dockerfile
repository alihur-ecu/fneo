# Pinned ontology-validation image.
# ROBOT 1.9.11 bundles HermiT. The jar is downloaded at build time and is not
# committed. Checksum recorded from the GitHub release asset on 2026-11-06.
FROM eclipse-temurin:17-jre-jammy

ARG ROBOT_URL=https://github.com/ontodev/robot/releases/download/v1.9.11/robot.jar
ARG ROBOT_SHA256=53cd275c8e4c0dad1fc2c1c34174876795cd7d6b6926e1444adcbb0cb3c7ab26

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL -o /opt/robot.jar "${ROBOT_URL}" \
    && echo "${ROBOT_SHA256}  /opt/robot.jar" | sha256sum -c - \
    && printf '#!/bin/sh\nexec java -jar /opt/robot.jar "$@"\n' > /usr/local/bin/robot \
    && chmod +x /usr/local/bin/robot

WORKDIR /work
ENTRYPOINT ["robot"]

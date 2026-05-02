# Reference: a minimal vanilla Minecraft image.
#
# The installer's "create a default Minecraft server" option uses the
# upstream image `itzg/minecraft-server` because it is already battle-tested
# and supports many Minecraft variants out of the box. This Dockerfile is
# kept as a reference if you want to bake your own image.
FROM eclipse-temurin:21-jre-jammy

ARG MC_VERSION=1.21.1
ARG MC_URL=https://piston-data.mojang.com/v1/objects/example/server.jar

ENV EULA=FALSE \
    MEMORY=1024M \
    DATA_DIR=/data

RUN groupadd -g 1000 minecraft && \
    useradd -u 1000 -g 1000 -d /data -m -s /bin/false minecraft && \
    mkdir -p /data && chown -R 1000:1000 /data

USER 1000:1000
WORKDIR /data

ADD --chown=1000:1000 ${MC_URL} /data/server.jar

EXPOSE 25565
VOLUME ["/data"]

CMD ["sh", "-c", "echo \"eula=$EULA\" > /data/eula.txt && exec java -Xmx${MEMORY} -Xms${MEMORY} -jar /data/server.jar nogui"]

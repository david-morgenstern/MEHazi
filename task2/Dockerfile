# Spark with the pipeline and the Postgres driver baked in. Nothing is
# bind-mounted, so the image runs the same under compose or a bare docker run.
FROM apache/spark:4.0.1

USER root

# The JDBC driver has to be on the classpath before the JVM starts, which is why
# it is in the image rather than resolved with --packages at submit time.
ADD --chmod=644 \
    https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.4/postgresql-42.7.4.jar \
    /opt/spark/jars/postgresql.jar

# Where the parquet handover between the two stages lives. A named volume
# mounted here inherits this ownership, so the unprivileged user can write.
RUN mkdir -p /data && chown 185:185 /data

COPY main.py load.py /opt/app/

USER 185
WORKDIR /opt/app

# One JVM, all the cores the container is given. Which script it runs is the
# command, so the same image is both the pipeline and the loader.
ENTRYPOINT ["/opt/spark/bin/spark-submit", "--master", "local[*]", "--driver-memory", "2g"]
CMD ["main.py"]

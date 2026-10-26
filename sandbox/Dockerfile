FROM gcc:12-bookworm

RUN apt-get update \
    && apt-get install --no-install-recommends -y python3 \
    && rm -rf /var/lib/apt/lists/*

COPY runner/runner.py /usr/local/bin/autograder-runner
RUN chmod 0555 /usr/local/bin/autograder-runner \
    && useradd --uid 1000 --create-home --shell /usr/sbin/nologin grader

ENTRYPOINT ["/usr/local/bin/autograder-runner"]

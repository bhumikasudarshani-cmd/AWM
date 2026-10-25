import logging

log = logging.getLogger(__name__)


def process(job):
    log.info("processing job %s", job.id)
    return job.run()

FROM public.ecr.aws/docker/library/python:3.12.11-alpine3.22@sha256:efcdfa6a6b2fd2afb9c7dfa9a5b288a6f68338b5cfdebe6b637d986067d85757
COPY --chmod=0444 integrations/inspect_tool_execution/sandbox/registry.py /opt/registry.py
COPY --chmod=0444 integrations/inspect_tool_execution/sandbox/snapshot.py /opt/snapshot.py
COPY --chmod=0444 integrations/inspect_v3_bridge/sandbox/producer.py /opt/producer.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
WORKDIR /state
CMD ["sleep", "infinity"]

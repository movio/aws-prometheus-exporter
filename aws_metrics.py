# -*- coding: utf-8 -*-

import re
import sys
import time
import threading
from collections import namedtuple

import yaml
import boto3
from prometheus_client import REGISTRY, Gauge, start_http_server

AwsMetric = namedtuple("AwsMetric", [
    "name",
    "description",
    "service",
    "paginator",
    "paginator_args",
    "update_freq_mins",
    "search"
])

class MetricThread(threading.Thread):
    def __init__(self, metric, registry, session):
        super().__init__()
        self.metric = metric
        self.registry = registry
        self.session = session

        self.gauge = None

    def _step(self):
        resps = list(self._get_response_iterator())
        keys = resps and [k for k in resps[0].keys() if k != "value"]
        gauge = self._get_gauge(self.metric.name, self.metric.description, keys)
        for resp in resps:
            value = resp.pop("value")
            assert list(resp.keys()) == keys
            gauge.labels(*resp.values()).set(value)
            
    def _get_response_iterator(self):
        service = self.session.client(self.metric.service)
        paginator = service.get_paginator(self.metric.paginator)
        response_iterator = paginator.paginate(**self.metric.paginator_args)
        return response_iterator.search(self.metric.search)

    def _get_gauge(self, name, description, labels):
        if self.gauge:
            return self.gauge
        else:
            gauge = Gauge(name, description, labels, registry=self.registry)
            self.gauge = gauge
            return gauge

    def run(self):
        while True:
            self._step()
            time.sleep(self.metric.update_freq_mins * 60)

_VALID_METRIC_NAME_RE = re.compile("^[a-z_0-9]+$")

def _parse_metrics(yaml_string):
    obj = yaml.load(yaml_string)
    ret = []
    for metric_name, parsed_metric in obj.items():
        if not _VALID_METRIC_NAME_RE.match(metric_name):
            raise ValueError("metric name '%s' does not match [a-z_0-9]+" % metric_name)
            
        def get_field(field):
            ret = parsed_metric.get(field)
            if ret is None:
                raise ValueError("metric '%s' is missing mandatory field '%s'" % (metric_name, field))
            return ret
            
        ret.append(AwsMetric(
            name=metric_name,
            description=get_field("description").strip(),
            service=get_field("service").strip(),
            paginator=get_field("paginator").strip(),
            paginator_args=parsed_metric.get("paginator_args", {}),
            update_freq_mins=parsed_metric.get("update_freq_mins", 5),
            search=get_field("search").strip()
        ))

    return ret

if __name__ == "__main__":
    with open(sys.argv[1]) as f:
        cfg = f.read()
    registry = REGISTRY
    session = boto3.session.Session()

    metrics = _parse_metrics(cfg)
    for metric in metrics:
        thread = MetricThread(metric, registry, session)
        thread.start()

    start_http_server(8000)
    print("Server started.")

    while True:
        time.sleep(1000)

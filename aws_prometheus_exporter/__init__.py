# -*- coding: utf-8 -*-

import re
import sys
import time
import datetime
import threading
from collections import namedtuple

import yaml
import boto3
from prometheus_client import REGISTRY, Gauge, start_http_server

__all__ = ["AwsMetric", "AwsMetricCollectorThread", "parse_aws_metrics"]

AwsMetric = namedtuple("AwsMetric", [
    "name",
    "description",
    "service",
    "paginator",
    "paginator_args",
    "update_freq_mins",
    "search"
])


class AwsMetricCollectorThread(threading.Thread):

    def __init__(self, metric, registry, session):
        super().__init__()
        self.metric = metric
        self.registry = registry
        self.session = session
        self.gauge = None

    def _get_paginator_args(self):
        if isinstance(self.metric.paginator_args, dict):
            return self.metric.paginator_args
        elif isinstance(self.metric.paginator_args, str):
            d = eval(self.metric.paginator_args, {
                "datetime": datetime.datetime
            })
            if not isinstance(d, dict):
                raise ValueError("paginator_args '%s' should eval to a dict" % self.metric.paginator_args)
            return d
        else:
            raise ValueError("paginator_args '%s' should either be or eval to a dict" % self.metric.paginator_args)

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
        response_iterator = paginator.paginate(**self._get_paginator_args())
        return response_iterator.search(self.metric.search)

    def _get_gauge(self, name, description, labels):
        if self.gauge:
            return self.gauge
        # pylint: disable=unexpected-keyword-arg
        gauge = Gauge(name, description, labels, registry=self.registry)
        self.gauge = gauge
        return gauge

    def run(self):
        while True:
            self._step()
            time.sleep(self.metric.update_freq_mins * 60)


VALID_METRIC_NAME_RE = re.compile("^[a-z_0-9]+$")


def parse_aws_metrics(yaml_string):
    parsed_yaml = yaml.load(yaml_string)
    metrics = []

    def get_field(field_name, metric_name, parsed_metric):
        field_value = parsed_metric.get(field_name)
        if field_value is None:
            raise ValueError("metric '%s' is missing mandatory field '%s'" % (metric_name, field_name))
        return field_value

    for metric_name, parsed_metric in parsed_yaml.items():
        if not VALID_METRIC_NAME_RE.match(metric_name):
            raise ValueError("metric name '%s' does not match [a-z_0-9]+" % metric_name)

        metrics.append(AwsMetric(
            name=metric_name,
            description=get_field("description", metric_name, parsed_metric).strip(),
            service=get_field("service", metric_name, parsed_metric).strip(),
            paginator=get_field("paginator", metric_name, parsed_metric).strip(),
            paginator_args=parsed_metric.get("paginator_args", {}),
            update_freq_mins=parsed_metric.get("update_freq_mins", 5),
            search=get_field("search", metric_name, parsed_metric).strip()
        ))

    return metrics


def main():
    # FIXME: add argparse
    with open(sys.argv[1]) as metrics_file:
        cfg = metrics_file.read()
    registry = REGISTRY

    metrics = parse_aws_metrics(cfg)
    for metric in metrics:
        session = boto3.session.Session()
        thread = AwsMetricCollectorThread(metric, registry, session)
        thread.start()

    start_http_server(8000)
    print("Server started.")

    while True:
        time.sleep(1000)


if __name__ == "__main__":
    main()

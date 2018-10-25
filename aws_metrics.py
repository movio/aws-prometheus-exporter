# -*- coding: utf-8 -*-

import re
from collections import namedtuple

import yaml
from prometheus_client import Gauge

AwsMetric = namedtuple("AwsMetric", [
    "name",
    "description",
    "type",
    "value_label",
    "service",
    "paginator",
    "filters",
    "search"
])

VALID_TYPES = [
    "array_to_unit_gauge"
]


class AwsMetricsCollector:

    VALID_METRIC_NAME_RE = re.compile("^[a-z_0-9]+$")

    def __init__(self, yaml_string, collector_registry=None):
        parsed_metrics = yaml.load(yaml_string)
        self.metrics = tuple(self._create_aws_metric(k, v) for k, v in parsed_metrics.items())
        self.registry = collector_registry
        self.gauges = {}

    def run(self, boto3_session, label_names, label_values):
        for metric in self.metrics:
            self._run_metric(metric, boto3_session, label_names, label_values)

    def _run_metric(self, metric, boto3_session, label_names, label_values):
        if metric.type == "array_to_unit_gauge":
            return self._run_array_to_unit_gauge_metric(metric, boto3_session, label_names, label_values)
        raise ValueError("Unknow metric type: '%s'" % metric.type)

    def _run_array_to_unit_gauge_metric(self, metric, boto3_session, label_names, label_values):
        gauge = self._get_gauge(metric.name, metric.description, label_names + [metric.value_label])
        for value in self._get_response_iterator(boto3_session, metric):
            gauge.labels(*(label_values + [value])).set(1)
        return gauge

    def _get_gauge(self, name, description, labels):
        # pylint: disable=unexpected-keyword-arg
        if name not in self.gauges:
            self.gauges[name] = Gauge(name, description, labels, registry=self.registry)
        return self.gauges[name]

    @staticmethod
    def _get_response_iterator(boto3_session, metric):
        service = boto3_session.client(metric.service)
        paginator = service.get_paginator(metric.paginator)
        response_iterator = paginator.paginate(Filters=metric.filters)
        return response_iterator.search(metric.search)

    @classmethod
    def _create_aws_metric(cls, metric_name, parsed_metric):
        if not cls.VALID_METRIC_NAME_RE.match(metric_name):
            raise ValueError("metric name '%s' does not match [a-z_0-9]+" % metric_name)
        for field in ('description', 'type', 'service', 'paginator', 'search'):
            if field not in parsed_metric:
                raise ValueError("metric '%s' is missing mandatory field '%s'" % (metric_name, field))
        if 'filters' not in parsed_metric:
            parsed_metric['filters'] = []
        if parsed_metric['type'] not in VALID_TYPES:
            raise ValueError("metric '%s' has unknown type '%s'" % (metric_name, parsed_metric['type']))
        if parsed_metric['type'] == "array_to_unit_gauge" and "value_label" not in parsed_metric:
            raise ValueError("metric '%s' of type 'array_to_unit_gauge' must have a 'value_label' field" % metric_name)
        if 'value_label' not in parsed_metric:
            parsed_metric['value_label'] = None
        return AwsMetric(
            name=metric_name,
            description=parsed_metric["description"],
            type=parsed_metric['type'],
            value_label=parsed_metric["value_label"],
            filters=parsed_metric["filters"],
            service=parsed_metric["service"],
            paginator=parsed_metric["paginator"],
            search=parsed_metric["search"]
        )

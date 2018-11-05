# -*- coding: utf-8 -*-

import re
import sys
import time
import datetime
import argparse
import unittest.mock as mock
from collections import namedtuple
from threading import Thread, Lock, Event

import yaml
import boto3
import jmespath
from prometheus_client.core import REGISTRY, GaugeMetricFamily
from prometheus_client import start_http_server

__all__ = ["AwsMetric", "AwsMetricsCollector", "parse_aws_metrics"]


VALID_METRIC_NAME_RE = re.compile("^[a-z_0-9]+$")

AwsMetric = namedtuple("AwsMetric", [
    "name",
    "description",
    "service",
    "method",
    "method_args",
    "use_paginator",
    "label_names",
    "search"
])

AwsMetric.__doc__ = """
AwsMetric object describe a Gauge obtained from a boto3 API call.

name: the Prometheus metric name (must match ^[a-z_0-9]+$)
description: the Prometheus metric description
service: the AWS service, as per boto3.Session::client(service)
method: the name of the boto3 client method or paginator (e.g. 'list_objects' for the 's3' service)
method_args: kwargs to be given to the client method or paginator
use_paginator: set to True to use a paginator instead of a client method
search: JMESPath expression used for client-side filtration and projection (must evaluate to a list of dicts)
label_names: keys of the dicts returned by the JMESPath expression (also the label names of the Prometheus gauge)
"""


class AwsMetricsCollector:
    """
    Prometheus Collector for AwsMetric objects. Must be registered with a CollectorRegistry.
    Call update() periodically to refresh the gauge values (this method is thread-safe).
    See __main__.py for an example of usage.
    """

    def __init__(self, metrics, session, label_names=None, label_values=None):
        """
        metrics: a list of AwsMetric objects
        session: a boto3 session with an AWS region_name configured
        label_names (optional): a list of extra labels names to add to the underlying GaugeMetricFamily
        label_values (optional): corresponding values for label_names
        """
        super().__init__()
        self._session = session
        self._metrics = metrics
        self._data_lock = Lock()
        self._data = {}  # dict of metric_name to list of (label_values, value)
        self._label_names = label_names or []
        self._label_values = label_values or []

    def update(self):
        """
        Makes the boto3 API calls, collects the results, and stores them for use when collect() gets
        called by prometheus_client. Should be called regularly to maintain up-to-date metrics.
        Calling this too frequently may cause Rate Exceeded errors.
        This method is thread-safe.
        """
        with self._data_lock:
            self._data = {}
            for metric in self._metrics:
                self._data[metric.name] = self._collect_metric(metric)

    def collect(self):
        """
        Yields GaugeMetricFamily objects, as expected by CollectorRegistry.
        This method is thread-safe.
        """
        with self._data_lock:
            for m in self._metrics:
                gauge = GaugeMetricFamily(m.name, m.description, labels=self._label_names + m.label_names)
                for (label_values, value) in self._data.get(m.name, []):
                    gauge.add_metric(label_values, value)
                yield gauge

    def _collect_metric(self, metric):
        responses = self._call_paginator(metric) if metric.use_paginator else self._call_service_method(metric)
        assert all(isinstance(r, dict) for r in responses), "responses '%s' must a sequence of dicts" % responses
        result = []
        for response in responses:
            assert "value" in response, "response object '%s' is missing a 'value' property" % response
            assert isinstance(response["value"], (float, int)), "the `value` property must be a number"
            value = response.pop("value")
            labels = [response[label] if response[label] is not None else '<null>' for label in metric.label_names]
            result.append((self._label_values + labels, value))
        return result

    def _call_paginator(self, metric):
        service = self._session.client(metric.service)
        paginator = service.get_paginator(metric.method)
        paginate_response_iterator = paginator.paginate(**metric.method_args)
        return list(paginate_response_iterator.search(metric.search))

    def _call_service_method(self, metric):
        service = self._session.client(metric.service)
        service_method = getattr(service, metric.method)
        next_token = ''
        responses = []
        kwargs = dict(**metric.method_args)
        while next_token is not None:
            response = service_method(**kwargs)
            next_token = response.get('NextToken', None)
            responses += jmespath.search(metric.search, response)
            kwargs["NextToken"] = next_token
        return responses


def parse_aws_metrics(yaml_string):
    """
    Parses a YAML-formatted document and returns a list of AwsMetric objects.
    """
    parsed_yaml = yaml.load(yaml_string)
    metrics = []

    def get_field(field_name, metric_name, parsed_metric):
        field_value = parsed_metric.get(field_name)
        if field_value is None:
            raise ValueError("metric '%s' is missing mandatory field '%s'" % (metric_name, field_name))
        return field_value

    def eval_paginator_args(paginator_args):
        # pylint: disable=eval-used
        if isinstance(paginator_args, dict):
            return paginator_args
        if isinstance(paginator_args, str):
            paginator_args = eval(paginator_args, {"datetime": datetime.datetime, "timedelta": datetime.timedelta})
            if not isinstance(paginator_args, dict):
                raise ValueError("paginator_args '%s' should eval to a dict" % paginator_args)
            return paginator_args
        raise ValueError("paginator_args '%s' is not a str or dict" % paginator_args)

    for metric_name, parsed_metric in parsed_yaml.items():
        if not VALID_METRIC_NAME_RE.match(metric_name):
            raise ValueError("metric name '%s' does not match ^[a-z_0-9]+$" % metric_name)
        if 'paginator' in parsed_metric:
            method_field = "paginator"
            method_args_field = "paginator_args"
            use_paginator = True
        elif 'method' in parsed_metric:
            method_field = "method"
            method_args_field = "method_args"
            use_paginator = False
        else:
            raise ValueError("metric name '%s' does not have a 'paginator' or 'method' property" % metric_name)
        metrics.append(AwsMetric(
            name=metric_name,
            description=get_field("description", metric_name, parsed_metric).strip(),
            service=get_field("service", metric_name, parsed_metric).strip(),
            method=get_field(method_field, metric_name, parsed_metric).strip(),
            method_args=eval_paginator_args(parsed_metric.get(method_args_field, {})),
            use_paginator=use_paginator,
            label_names=get_field("label_names", metric_name, parsed_metric),
            search=get_field("search", metric_name, parsed_metric).strip(),
        ))

    return metrics

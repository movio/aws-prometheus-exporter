# -*- coding: utf-8 -*-

import time
import argparse

import boto3

from aws_prometheus_exporter import AwsMetric, AwsMetricsCollector, parse_aws_metrics
from prometheus_client import REGISTRY, start_http_server


def parse_args():
    parser = argparse.ArgumentParser(
        description='AWS Prometheus Exporter'
    )
    parser.add_argument(
        '-f', '--metrics-file',
        metavar='PATH',
        dest='metrics_file_path',
        required=True,
        type=str,
        help='path to a YAML-formatted metrics file'
    )
    parser.add_argument(
        '-p', '--port',
        metavar='PORT',
        dest="port",
        required=True,
        type=int,
        help='listen to this port'
    )
    parser.add_argument(
        '-s', '--period-seconds',
        metavar='SECONDS',
        dest="period_seconds",
        required=False,
        type=int,
        default=300,
        help='seconds between metric refreshes'
    )
    return parser.parse_args()


def main(args):
    port = int(args.port)
    with open(args.metrics_file_path) as metrics_file:
        metrics_yaml = metrics_file.read()
    metrics = parse_aws_metrics(metrics_yaml)
    collector = AwsMetricsCollector(metrics, boto3.Session())
    REGISTRY.register(collector)
    start_http_server(port)
    print("Serving at port: %s" % port)
    while True:
        try:
            collector.update()
            time.sleep(args.period_seconds)
        except KeyboardInterrupt:
            print("Caught SIGTERM - stopping...")
            break
    print("Done.")


main(parse_args())

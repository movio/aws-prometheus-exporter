# -*- coding: utf-8 -*-

import unittest.mock as mock
from collections import namedtuple
import datetime

from aws_prometheus_exporter import parse_aws_metrics, AwsMetric, AwsMetricsCollector
from prometheus_client.core import Sample

# pylint: disable=protected-access

SINGLE_METRIC_YAML = """
ec2_instance_ids:
  description: EC2 instance ids
  service: ec2
  paginator: describe_instances
  paginator_args:
    Filters:
      - Name: instance-state-name
        Values: [ "Running" ]
  label_names:
    - id
  search: |
    Reservations[].Instances[].{id: InstanceId, value: `1`}[]
"""

SINGLE_METRIC_YAML_NEEDING_EVAL = """
recent_emr_cluster_ids:
  description: Recent EMR cluster ids
  service: emr
  paginator: list_clusters
  paginator_args: |
    {
        "CreatedAfter": datetime(2018,1,1) - timedelta(weeks=4)
    }
  label_names:
    - id
  search: |
    Clusters[].{id: Id, value: `1`}
"""


MULTIPLE_METRICS_YAML = """
public_ec2_instance_ids:
  description: EC2 instance ids of instances with a public IP
  service: ec2
  paginator: describe_instances
  paginator_args:
    Filters:
      - Name: instance-state-name
        Values: [ "Running" ]
  label_names:
    - id
  search: |
    Reservations[].Instances[?PublicIpAddress].{id: InstanceId, value: `1`}[]

ssm_agents_ec2_instance_ids:
  description: EC2 instance ids of instances with SSM agent
  service: ssm
  paginator: describe_instance_information
  paginator_args:
    Filters:
      - Key: ResourceType
        Values: [ "EC2Instance" ]
      - Key: PingStatus
        Values: [ "Online" ]
  label_names:
    - id
  search: |
    InstanceInformationList[].{id: InstanceId, value: `1`}[]
"""


def test_load_single_aws_metric():
    metrics = parse_aws_metrics(SINGLE_METRIC_YAML)
    assert len(metrics) == 1
    ec2_instance_ids = metrics[0]
    assert ec2_instance_ids == AwsMetric(
        name="ec2_instance_ids",
        description="EC2 instance ids",
        service="ec2",
        paginator="describe_instances",
        paginator_args={
            "Filters": [{
                "Name": "instance-state-name",
                "Values": ["Running"]
            }]
        },
        label_names=["id"],
        search="Reservations[].Instances[].{id: InstanceId, value: `1`}[]"
    )


def test_load_single_aws_metric_needing_eval():
    metrics = parse_aws_metrics(SINGLE_METRIC_YAML_NEEDING_EVAL)
    assert len(metrics) == 1
    ec2_instance_ids = metrics[0]
    assert ec2_instance_ids == AwsMetric(
        name="recent_emr_cluster_ids",
        description="Recent EMR cluster ids",
        service="emr",
        paginator="list_clusters",
        paginator_args={
            "CreatedAfter": datetime.datetime(2017, 12, 4, 0, 0)
        },
        label_names=["id"],
        search="Clusters[].{id: Id, value: `1`}"
    )


def test_load_multiple_aws_metrics():
    metrics = parse_aws_metrics(MULTIPLE_METRICS_YAML)
    assert len(metrics) == 2
    assert metrics[0] == AwsMetric(
        name="public_ec2_instance_ids",
        description="EC2 instance ids of instances with a public IP",
        service="ec2",
        paginator="describe_instances",
        paginator_args={
            "Filters": [{
                "Name": "instance-state-name",
                "Values": ["Running"]
            }]
        },
        label_names=["id"],
        search="Reservations[].Instances[?PublicIpAddress].{id: InstanceId, value: `1`}[]"
    )
    assert metrics[1] == AwsMetric(
        name="ssm_agents_ec2_instance_ids",
        description="EC2 instance ids of instances with SSM agent",
        service="ssm",
        paginator_args={
            "Filters": [
                {
                    "Key": "ResourceType",
                    "Values": ["EC2Instance"]
                },
                {
                    "Key": "PingStatus",
                    "Values": ["Online"],
                }
            ]
        },
        paginator="describe_instance_information",
        label_names=["id"],
        search="InstanceInformationList[].{id: InstanceId, value: `1`}[]"
    )


SessionMocks = namedtuple("SessionMocks", [
    "session",
    "service",
    "paginator",
    "paginate_response_iterator"
])


def create_session_mocks(search_response_iterator):
    session = mock.NonCallableMagicMock()
    paginator = mock.NonCallableMagicMock()
    service = mock.NonCallableMagicMock()
    paginate_response_iterator = mock.NonCallableMagicMock()
    paginate_response_iterator.search = mock.Mock(return_value=search_response_iterator)
    paginator.paginate = mock.Mock(return_value=paginate_response_iterator)
    service.get_paginator = mock.Mock(return_value=paginator)
    session.client = mock.Mock(return_value=service)
    return SessionMocks(session, service, paginator, paginate_response_iterator)


def test_collect_metric():
    mocks = create_session_mocks([
        {"id": "instance_id_1", "value": 1},
        {"id": "instance_id_2", "value": 1},
        {"id": "instance_id_3", "value": 1}
    ])
    metrics = parse_aws_metrics(SINGLE_METRIC_YAML)
    collector = AwsMetricsCollector(metrics, mocks.session)
    collector.update()
    gauge_family = list(collector.collect())[0]
    mocks.session.client.assert_called_once_with("ec2")
    mocks.service.get_paginator.assert_called_once_with("describe_instances")
    mocks.paginator.paginate.assert_called_once_with(Filters=[{
        "Name": "instance-state-name",
        "Values": ["Running"]
    }])
    mocks.paginate_response_iterator.search.assert_called_once_with(metrics[0].search)
    assert gauge_family.samples == [
        Sample("ec2_instance_ids", {"id": "instance_id_1"}, 1),
        Sample("ec2_instance_ids", {"id": "instance_id_2"}, 1),
        Sample("ec2_instance_ids", {"id": "instance_id_3"}, 1)
    ]


def test_collect_metric_convert_nulls():
    mocks = create_session_mocks([
        {"id": None, "value": 1},
        {"id": None, "value": 1},
        {"id": "instance_id_3", "value": 1}
    ])
    metrics = parse_aws_metrics(SINGLE_METRIC_YAML)
    collector = AwsMetricsCollector(metrics, mocks.session)
    collector.update()
    gauge_family = list(collector.collect())[0]
    mocks.session.client.assert_called_once_with("ec2")
    mocks.service.get_paginator.assert_called_once_with("describe_instances")
    mocks.paginator.paginate.assert_called_once_with(Filters=[{
        "Name": "instance-state-name",
        "Values": ["Running"]
    }])
    mocks.paginate_response_iterator.search.assert_called_once_with(metrics[0].search)
    assert gauge_family.samples == [
        Sample("ec2_instance_ids", {"id": "<null>"}, 1),
        Sample("ec2_instance_ids", {"id": "<null>"}, 1),
        Sample("ec2_instance_ids", {"id": "instance_id_3"}, 1)
    ]


def test_collect_metric_with_extra_labels():
    mocks = create_session_mocks([
        {"id": "instance_id_1", "value": 1},
        {"id": "instance_id_2", "value": 1},
        {"id": "instance_id_3", "value": 1}
    ])
    metrics = parse_aws_metrics(SINGLE_METRIC_YAML)
    collector = AwsMetricsCollector(metrics, mocks.session, ["region_name", "env"], ["us-east-1", "dev"])
    collector.update()
    gauge_family = list(collector.collect())[0]
    mocks.session.client.assert_called_once_with("ec2")
    mocks.service.get_paginator.assert_called_once_with("describe_instances")
    mocks.paginator.paginate.assert_called_once_with(Filters=[{
        "Name": "instance-state-name",
        "Values": ["Running"]
    }])
    mocks.paginate_response_iterator.search.assert_called_once_with(metrics[0].search)
    assert gauge_family.samples == [
        Sample("ec2_instance_ids", {"region_name": "us-east-1", "env": "dev", "id": "instance_id_1"}, 1),
        Sample("ec2_instance_ids", {"region_name": "us-east-1", "env": "dev", "id": "instance_id_2"}, 1),
        Sample("ec2_instance_ids", {"region_name": "us-east-1", "env": "dev", "id": "instance_id_3"}, 1)
    ]

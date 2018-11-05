# -*- coding: utf-8 -*-

from unittest import mock
from unittest.mock import call

from collections import namedtuple
import datetime

from prometheus_client.core import Sample
from aws_prometheus_exporter import parse_aws_metrics, AwsMetric, AwsMetricsCollector

# pylint: disable=protected-access

SINGLE_METRIC_YAML_WITH_PAGINATOR = """
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

SINGLE_METRIC_YAML_WITH_PAGINATOR_WITH_SERVICE_METHOD = """
ec2_instance_ids:
  description: EC2 instance ids
  service: ec2
  method: describe_instances
  method_args:
    Filters:
      - Name: instance-state-name
        Values: [ "Running" ]
  label_names:
    - id
  search: |
    Reservations[].Instances[].{id: InstanceId, value: `1`}[]
"""

SINGLE_METRIC_YAML_WITH_PAGINATOR_NEEDING_EVAL = """
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
    metrics = parse_aws_metrics(SINGLE_METRIC_YAML_WITH_PAGINATOR)
    assert len(metrics) == 1
    ec2_instance_ids = metrics[0]
    assert ec2_instance_ids == AwsMetric(
        name="ec2_instance_ids",
        description="EC2 instance ids",
        service="ec2",
        method="describe_instances",
        method_args={
            "Filters": [{
                "Name": "instance-state-name",
                "Values": ["Running"]
            }]
        },
        use_paginator=True,
        label_names=["id"],
        search="Reservations[].Instances[].{id: InstanceId, value: `1`}[]"
    )


def test_load_single_aws_metric_needing_eval():
    metrics = parse_aws_metrics(SINGLE_METRIC_YAML_WITH_PAGINATOR_NEEDING_EVAL)
    assert len(metrics) == 1
    ec2_instance_ids = metrics[0]
    assert ec2_instance_ids == AwsMetric(
        name="recent_emr_cluster_ids",
        description="Recent EMR cluster ids",
        service="emr",
        method="list_clusters",
        method_args={
            "CreatedAfter": datetime.datetime(2017, 12, 4, 0, 0)
        },
        use_paginator=True,
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
        method="describe_instances",
        method_args={
            "Filters": [{
                "Name": "instance-state-name",
                "Values": ["Running"]
            }]
        },
        use_paginator=True,
        label_names=["id"],
        search="Reservations[].Instances[?PublicIpAddress].{id: InstanceId, value: `1`}[]"
    )
    assert metrics[1] == AwsMetric(
        name="ssm_agents_ec2_instance_ids",
        description="EC2 instance ids of instances with SSM agent",
        service="ssm",
        method="describe_instance_information",
        method_args={
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
        use_paginator=True,
        label_names=["id"],
        search="InstanceInformationList[].{id: InstanceId, value: `1`}[]"
    )


SessionMocksUsingPaginator = namedtuple("SessionMocksUsingPaginator", [
    "session",
    "service",
    "paginator",
    "paginate_response_iterator"
])


def create_session_mocks_using_paginator(search_response_iterator):
    session = mock.NonCallableMagicMock()
    paginator = mock.NonCallableMagicMock()
    service = mock.NonCallableMagicMock()
    paginate_response_iterator = mock.NonCallableMagicMock()
    paginate_response_iterator.search = mock.Mock(return_value=search_response_iterator)
    paginator.paginate = mock.Mock(return_value=paginate_response_iterator)
    service.get_paginator = mock.Mock(return_value=paginator)
    session.client = mock.Mock(return_value=service)
    return SessionMocksUsingPaginator(session, service, paginator, paginate_response_iterator)


def test_collect_metric():
    mocks = create_session_mocks_using_paginator([
        {"id": "instance_id_1", "value": 1},
        {"id": "instance_id_2", "value": 1},
        {"id": "instance_id_3", "value": 1}
    ])
    metrics = parse_aws_metrics(SINGLE_METRIC_YAML_WITH_PAGINATOR)
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


SessionMocksUsingServiceMethod = namedtuple("SessionMocksUsingServiceMethod", [
    "session",
    "service",
    "method",
])


def create_session_mocks_using_service_method(method, method_responses):
    session = mock.NonCallableMagicMock()
    service = mock.NonCallableMagicMock()
    setattr(service, method, mock.Mock(side_effect=method_responses))
    session.client = mock.Mock(return_value=service)
    return SessionMocksUsingServiceMethod(
        session,
        service,
        getattr(service, method)
    )


def test_collect_metric_using_service_method():
    mocks = create_session_mocks_using_service_method("describe_instances", [
        {
            "Reservations": [{"Instances": [{"InstanceId": "instance_id_1"}, {"InstanceId": "instance_id_2"}, ]}],
            "NextToken": "123abc"
        },
        {
            "Reservations": [{"Instances": [{"InstanceId": "instance_id_3"}]}],
            "NextToken": None
        },
    ])
    metrics = parse_aws_metrics(SINGLE_METRIC_YAML_WITH_PAGINATOR_WITH_SERVICE_METHOD)
    collector = AwsMetricsCollector(metrics, mocks.session)
    collector.update()
    gauge_family = list(collector.collect())[0]
    mocks.session.client.assert_called_once_with("ec2")
    mocks.service.describe_instances.assert_has_calls([
        call(Filters=[{
            "Name": "instance-state-name",
            "Values": ["Running"],
        }]),
        call(Filters=[{
            "Name": "instance-state-name",
            "Values": ["Running"],
        }], NextToken="123abc")
    ])
    assert gauge_family.samples == [
        Sample("ec2_instance_ids", {"id": "instance_id_1"}, 1),
        Sample("ec2_instance_ids", {"id": "instance_id_2"}, 1),
        Sample("ec2_instance_ids", {"id": "instance_id_3"}, 1)
    ]


def test_collect_metric_convert_nulls():
    mocks = create_session_mocks_using_paginator([
        {"id": None, "value": 1},
        {"id": "", "value": 1},
        {"id": "instance_id_3", "value": 1}
    ])
    metrics = parse_aws_metrics(SINGLE_METRIC_YAML_WITH_PAGINATOR)
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
        Sample("ec2_instance_ids", {"id": ""}, 1),
        Sample("ec2_instance_ids", {"id": "instance_id_3"}, 1)
    ]


def test_collect_metric_with_extra_labels():
    mocks = create_session_mocks_using_paginator([
        {"id": "instance_id_1", "value": 1},
        {"id": "instance_id_2", "value": 1},
        {"id": "instance_id_3", "value": 1}
    ])
    metrics = parse_aws_metrics(SINGLE_METRIC_YAML_WITH_PAGINATOR)
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

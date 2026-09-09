# Mock provider: these tests do not create or contact AWS resources.
mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
}

variables {
  targets = { owned-site = "https://example.com/" }
}

run "low_cost_defaults" {
  command = plan
  assert {
    condition     = aws_dynamodb_table.observations.billing_mode == "PROVISIONED" && aws_dynamodb_table.observations.write_capacity == 5
    error_message = "Keep fixed low provisioned capacity for the learning baseline."
  }
  assert {
    condition     = aws_lambda_function.monitor.timeout == 60 && aws_lambda_function.monitor.memory_size == 256
    error_message = "Changes to per-request limits require a cost review."
  }
  assert {
    condition     = aws_scheduler_schedule.target["owned-site"].state == "DISABLED"
    error_message = "Monitoring must be opt-in."
  }
  assert {
    condition     = length(aws_sns_topic_subscription.email) == 0 && length(aws_iam_role.release) == 0
    error_message = "No default email subscription or GitHub trust."
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.heartbeat["owned-site"].treat_missing_data == "breaching"
    error_message = "Missing monitoring is an operational failure."
  }
}

run "too_many_targets" {
  command = plan
  variables {
    targets = { a = "https://example.com/", b = "https://example.com/", c = "https://example.com/", d = "https://example.com/", e = "https://example.com/", f = "https://example.com/" }
  }
  expect_failures = [var.targets]
}

run "reject_wildcard_oidc" {
  command = plan
  variables {
    github_oidc_subject = "repo:owner/*:environment:aws-learning"
  }
  expect_failures = [var.github_oidc_subject]
}

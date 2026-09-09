terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "ap-northeast-1"
  default_tags {
    tags = { Project = var.project, Environment = "learning", ManagedBy = "Terraform" }
  }
}

variable "project" {
  type    = string
  default = "mimamori-ops"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,24}$", var.project))
    error_message = "Use 3-25 lowercase letters, digits or hyphens."
  }
}

variable "targets" {
  type        = map(string)
  description = "1-5 owned or explicitly authorized HTTPS URLs. Do not commit customer URLs."
  validation {
    condition = length(var.targets) >= 1 && length(var.targets) <= 5 && alltrue([
      for id, url in var.targets : can(regex("^[a-z][a-z0-9-]{0,39}$", id)) &&
      can(regex("^https://[^/@?#:[:space:]]+(/[^?#[:space:]]*)?$", url))
    ])
    error_message = "Configure 1-5 lowercase target IDs and HTTPS URLs without credentials, query, port or fragment."
  }
}

variable "monitoring_enabled" {
  type        = bool
  default     = false
  description = "Enable only after cost, target permission and notification checks."
}

variable "notification_email" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Optional approved recipient; applying sends an SNS subscription confirmation."
}

variable "enable_email_notifications" {
  type    = bool
  default = false
}

variable "github_oidc_provider_arn" {
  type        = string
  default     = ""
  description = "Existing GitHub OIDC provider ARN. The stack does not create a shared account provider."
}

variable "github_oidc_subject" {
  type        = string
  default     = ""
  description = "Exact verified GitHub subject for aws-learning environment, including immutable IDs if used."
  validation {
    condition = var.github_oidc_subject == "" || (
      startswith(var.github_oidc_subject, "repo:") &&
      endswith(var.github_oidc_subject, ":environment:aws-learning") &&
      !strcontains(var.github_oidc_subject, "*")
    )
    error_message = "Use an exact repo subject ending in :environment:aws-learning; no wildcard."
  }
}

data "aws_caller_identity" "current" {}

resource "aws_dynamodb_table" "observations" {
  name           = var.project
  billing_mode   = "PROVISIONED"
  read_capacity  = 5
  write_capacity = 5
  hash_key       = "pk"
  range_key      = "sk"
  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "sk"
    type = "S"
  }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
  server_side_encryption { enabled = true }
}

resource "aws_sns_topic" "alerts" { name = "${var.project}-alerts" }

resource "aws_sns_topic_policy" "alarms" {
  arn = aws_sns_topic.alerts.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow", Principal = { Service = "cloudwatch.amazonaws.com" },
      Action = "sns:Publish", Resource = aws_sns_topic.alerts.arn,
      Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id },
      ArnLike = { "aws:SourceArn" = "arn:aws:cloudwatch:ap-northeast-1:${data.aws_caller_identity.current.account_id}:alarm:${var.project}-*" } }
    }]
  })
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.enable_email_notifications ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.notification_email
  lifecycle {
    precondition {
      condition     = var.notification_email != ""
      error_message = "An approved notification email is required."
    }
  }
}

resource "aws_sqs_queue" "dead_letter" {
  name                      = "${var.project}-failed-events"
  message_retention_seconds = 604800
  sqs_managed_sse_enabled   = true
}

resource "aws_cloudwatch_log_group" "monitor" {
  name              = "/aws/lambda/${var.project}"
  retention_in_days = 7
}

resource "aws_iam_role" "lambda" {
  name = "${var.project}-runtime"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole"
  }] })
}

resource "aws_iam_role_policy" "lambda" {
  role = aws_iam_role.lambda.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"],
    Resource = "${aws_cloudwatch_log_group.monitor.arn}:*" },
    { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"],
    Resource = aws_dynamodb_table.observations.arn },
    { Effect = "Allow", Action = ["sns:Publish"], Resource = aws_sns_topic.alerts.arn },
    { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = aws_sqs_queue.dead_letter.arn }
  ] })
}

resource "aws_lambda_function" "monitor" {
  function_name    = var.project
  role             = aws_iam_role.lambda.arn
  handler          = "mimamori.handler.handler"
  runtime          = "python3.13"
  architectures    = ["x86_64"]
  filename         = "${path.module}/lambda.zip"
  source_code_hash = filebase64sha256("${path.module}/lambda.zip")
  memory_size      = 256
  timeout          = 60
  publish          = true
  environment {
    variables = {
      TARGETS_JSON = jsonencode(var.targets)
      TABLE_NAME   = aws_dynamodb_table.observations.name
      TOPIC_ARN    = aws_sns_topic.alerts.arn
    }
  }
  depends_on = [aws_iam_role_policy.lambda]
  lifecycle {
    # Terraform bootstraps code; the release workflow subsequently owns code.
    ignore_changes = [filename, source_code_hash]
  }
}

resource "aws_lambda_alias" "live" {
  name             = "live"
  function_name    = aws_lambda_function.monitor.function_name
  function_version = aws_lambda_function.monitor.version
  lifecycle { ignore_changes = [function_version] }
}

resource "aws_lambda_function_event_invoke_config" "retries" {
  function_name                = aws_lambda_function.monitor.function_name
  qualifier                    = aws_lambda_alias.live.name
  maximum_event_age_in_seconds = 900
  maximum_retry_attempts       = 2
  destination_config {
    on_failure { destination = aws_sqs_queue.dead_letter.arn }
  }
}

resource "aws_scheduler_schedule_group" "monitor" { name = var.project }

resource "aws_iam_role" "scheduler" {
  name = "${var.project}-scheduler"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "scheduler.amazonaws.com" },
    Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id },
    ArnEquals = { "aws:SourceArn" = aws_scheduler_schedule_group.monitor.arn } }
  }] })
}

resource "aws_iam_role_policy" "scheduler" {
  role = aws_iam_role.scheduler.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = "lambda:InvokeFunction", Resource = aws_lambda_alias.live.arn },
    { Effect = "Allow", Action = "sqs:SendMessage", Resource = aws_sqs_queue.dead_letter.arn }
  ] })
}

resource "aws_scheduler_schedule" "target" {
  for_each            = var.targets
  name                = "${var.project}-${each.key}"
  group_name          = aws_scheduler_schedule_group.monitor.name
  schedule_expression = "rate(5 minutes)"
  state               = var.monitoring_enabled ? "ENABLED" : "DISABLED"
  flexible_time_window { mode = "OFF" }
  target {
    arn      = aws_lambda_alias.live.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ target_id = each.key, scheduled_time = "<aws.scheduler.scheduled-time>" })
    retry_policy {
      maximum_event_age_in_seconds = 900
      maximum_retry_attempts       = 2
    }
    dead_letter_config { arn = aws_sqs_queue.dead_letter.arn }
  }
  depends_on = [aws_iam_role_policy.scheduler, aws_lambda_function_event_invoke_config.retries]
}

resource "aws_cloudwatch_log_metric_filter" "heartbeat" {
  for_each       = var.targets
  name           = "${var.project}-${each.key}-completed"
  log_group_name = aws_cloudwatch_log_group.monitor.name
  pattern        = "{ $.event = \"check_complete\" && $.target_id = \"${each.key}\" && $.saved IS TRUE }"
  metric_transformation {
    name      = "Completed-${each.key}"
    namespace = var.project
    value     = "1"
  }
}

resource "aws_cloudwatch_metric_alarm" "heartbeat" {
  for_each            = var.targets
  alarm_name          = "${var.project}-${each.key}-no-checks"
  namespace           = var.project
  metric_name         = aws_cloudwatch_log_metric_filter.heartbeat[each.key].metric_transformation[0].name
  statistic           = "Sum"
  period              = 900
  evaluation_periods  = 1
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  treat_missing_data  = "breaching"
  actions_enabled     = var.monitoring_enabled
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name          = "${var.project}-lambda-errors"
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.monitor.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  actions_enabled     = var.monitoring_enabled
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "dlq" {
  alarm_name          = "${var.project}-failed-events"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dead_letter.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  treat_missing_data  = "notBreaching"
  actions_enabled     = var.monitoring_enabled
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_dashboard" "operations" {
  dashboard_name = var.project
  dashboard_body = jsonencode({ widgets = [
    { type = "metric", x = 0, y = 0, width = 12, height = 6, properties = {
      title = "Monitor errors and throttles", region = "ap-northeast-1", period = 300, stat = "Sum",
      metrics = [["AWS/Lambda", "Errors", "FunctionName", var.project],
      ["AWS/Lambda", "Throttles", "FunctionName", var.project]]
    } },
    { type = "metric", x = 12, y = 0, width = 12, height = 6, properties = {
      title   = "Monitor duration (ms)", region = "ap-northeast-1", period = 300, stat = "Maximum",
      metrics = [["AWS/Lambda", "Duration", "FunctionName", var.project]]
    } }
  ] })
}

resource "aws_iam_role" "release" {
  count = var.github_oidc_provider_arn != "" ? 1 : 0
  name  = "${var.project}-release"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect    = "Allow", Action = "sts:AssumeRoleWithWebIdentity",
    Principal = { Federated = var.github_oidc_provider_arn },
    Condition = { StringEquals = {
      "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub" = var.github_oidc_subject
    } }
  }] })
  lifecycle {
    precondition {
      condition     = var.github_oidc_subject != ""
      error_message = "Provide the exact verified OIDC subject."
    }
  }
}

resource "aws_iam_role_policy" "release" {
  count = length(aws_iam_role.release)
  role  = aws_iam_role.release[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{
    Effect = "Allow", Action = ["lambda:GetFunctionConfiguration", "lambda:GetAlias",
    "lambda:UpdateFunctionCode", "lambda:PublishVersion", "lambda:UpdateAlias", "lambda:InvokeFunction"],
    Resource = [aws_lambda_function.monitor.arn, "${aws_lambda_function.monitor.arn}:*"]
  }] })
}

output "function_name" { value = aws_lambda_function.monitor.function_name }
output "table_name" { value = aws_dynamodb_table.observations.name }
output "dead_letter_queue_url" { value = aws_sqs_queue.dead_letter.url }
output "release_role_arn" { value = try(aws_iam_role.release[0].arn, null) }

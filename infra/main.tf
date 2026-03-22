terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

# ── Variables ────────────────────────────────────────────
variable "project" {
  default = "callbot"
}

variable "app_port" {
  default = 8000
}

variable "instance_type" {
  default = "t3.small"
}

# ── Providers (no profile — uses EC2 IAM role) ──────────
provider "aws" {
  region = "us-east-1"
}

provider "aws" {
  alias  = "seoul"
  region = "ap-northeast-2"
}

# ── Data Sources ─────────────────────────────────────────
data "aws_vpc" "main" {
  provider = aws.seoul
  id       = "vpc-02a6622e06edfbd2d"
}

data "aws_subnets" "public" {
  provider = aws.seoul
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.main.id]
  }
  filter {
    name   = "map-public-ip-on-launch"
    values = ["true"]
  }
}

data "aws_ami" "amazon_linux_2023" {
  provider    = aws.seoul
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

data "aws_ec2_managed_prefix_list" "cloudfront" {
  provider = aws.seoul
  name     = "com.amazonaws.global.cloudfront.origin-facing"
}

# ── IAM Role ─────────────────────────────────────────────
resource "aws_iam_role" "app" {
  provider = aws.seoul
  name     = "${var.project}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "bedrock" {
  provider = aws.seoul
  name     = "bedrock-invoke"
  role     = aws_iam_role.app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      Resource = "*"
    }]
  })
}

resource "aws_iam_role_policy" "voice_io" {
  provider = aws.seoul
  name     = "voice-io"
  role     = aws_iam_role.app.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["transcribe:*"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["polly:SynthesizeSpeech", "polly:DescribeVoices"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  provider   = aws.seoul
  role       = aws_iam_role.app.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "app" {
  provider = aws.seoul
  name     = "${var.project}-profile"
  role     = aws_iam_role.app.name
}

# ── Key Pair ─────────────────────────────────────────────
resource "tls_private_key" "app" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "app" {
  provider   = aws.seoul
  key_name   = "${var.project}-key"
  public_key = tls_private_key.app.public_key_openssh
}

resource "local_file" "private_key" {
  content         = tls_private_key.app.private_key_pem
  filename        = "${path.module}/${var.project}-key.pem"
  file_permission = "0400"
}

# ── Security Groups ──────────────────────────────────────
resource "aws_security_group" "alb" {
  provider    = aws.seoul
  name        = "${var.project}-alb-sg"
  description = "Allow CloudFront traffic"
  vpc_id      = data.aws_vpc.main.id

  ingress {
    from_port       = 80
    to_port         = 80
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "ec2" {
  provider    = aws.seoul
  name        = "${var.project}-ec2-sg"
  description = "Security group for EC2 app"
  vpc_id      = data.aws_vpc.main.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port       = var.app_port
    to_port         = var.app_port
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ── ALB ──────────────────────────────────────────────────
resource "aws_lb" "main" {
  provider           = aws.seoul
  name               = "${var.project}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.public.ids
  ip_address_type    = "ipv4"
  idle_timeout       = 120
}

resource "aws_lb_target_group" "main" {
  provider    = aws.seoul
  name        = "${var.project}-tg"
  port        = var.app_port
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.main.id
  target_type = "instance"

  health_check {
    enabled             = true
    path                = "/health"
    port                = "traffic-port"
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 10
    healthy_threshold   = 3
    unhealthy_threshold = 2
  }
}

resource "aws_lb_listener" "http" {
  provider          = aws.seoul
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.main.arn
  }
}

# ── EC2 ──────────────────────────────────────────────────
resource "aws_instance" "app" {
  provider               = aws.seoul
  ami                    = data.aws_ami.amazon_linux_2023.id
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnets.public.ids[0]
  vpc_security_group_ids = [aws_security_group.ec2.id]
  key_name               = aws_key_pair.app.key_name
  iam_instance_profile   = aws_iam_instance_profile.app.name
  ebs_optimized          = true

  root_block_device {
    volume_size           = 30
    volume_type           = "gp3"
    delete_on_termination = true
  }

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
    http_endpoint               = "enabled"
  }

  user_data = <<-USERDATA
    #!/bin/bash
    set -ex
    dnf install -y python3.9 python3.9-pip git
    export HOME=/root
    curl -LsSf https://astral.sh/uv/install.sh | sh
    echo 'export PATH="/root/.local/bin:$PATH"' > /etc/profile.d/uv.sh
    mkdir -p /opt/${var.project}
    touch /tmp/userdata-complete
  USERDATA

  tags = {
    Name = "${var.project}-app"
  }
}

resource "aws_lb_target_group_attachment" "app" {
  provider         = aws.seoul
  target_group_arn = aws_lb_target_group.main.arn
  target_id        = aws_instance.app.id
  port             = var.app_port
}

# ── Elastic IP ───────────────────────────────────────────
resource "aws_eip" "app" {
  provider = aws.seoul
  domain   = "vpc"
}

resource "aws_eip_association" "app" {
  provider      = aws.seoul
  instance_id   = aws_instance.app.id
  allocation_id = aws_eip.app.id
}

# ── CloudFront ───────────────────────────────────────────
resource "aws_cloudfront_distribution" "main" {
  enabled         = true
  is_ipv6_enabled = true
  http_version    = "http2"
  price_class     = "PriceClass_All"

  origin {
    domain_name = aws_lb.main.dns_name
    origin_id   = aws_lb.main.dns_name

    custom_origin_config {
      http_port                = 80
      https_port               = 443
      origin_protocol_policy   = "http-only"
      origin_ssl_protocols     = ["TLSv1.2"]
      origin_read_timeout      = 60
      origin_keepalive_timeout = 60
    }
  }

  default_cache_behavior {
    target_origin_id       = aws_lb.main.dns_name
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    allowed_methods = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods  = ["GET", "HEAD"]

    # AWS Managed: CachingDisabled
    cache_policy_id          = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    # AWS Managed: AllViewer
    origin_request_policy_id = "216adef6-5c7f-47e4-b989-5492eafa07d3"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
    minimum_protocol_version       = "TLSv1.2_2021"
  }
}

# ── Outputs ──────────────────────────────────────────────
output "cloudfront_url" {
  value = "https://${aws_cloudfront_distribution.main.domain_name}"
}

output "ec2_public_ip" {
  value = aws_eip.app.public_ip
}

output "alb_dns" {
  value = aws_lb.main.dns_name
}

output "key_file" {
  value = local_file.private_key.filename
}

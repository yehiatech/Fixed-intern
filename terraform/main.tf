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
    local = {
      source  = "hashicorp/local"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Automatically generate an SSH Key Pair
resource "tls_private_key" "fenec_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "fenec_key_pair" {
  key_name   = "ai-callcenter-key"
  public_key = tls_private_key.fenec_key.public_key_openssh
}

# Save the private key locally as a .pem file
resource "local_file" "private_key" {
  content         = tls_private_key.fenec_key.private_key_pem
  filename        = "${path.module}/ai-callcenter-key.pem"
  file_permission = "0400"
}

# Security Group for the Firewall Ports
resource "aws_security_group" "fenec_sg" {
  name        = "fenec-ai-sg"
  description = "Allow SSH, CRM, and AI API traffic"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "EspoCRM Dashboard"
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "Voice API"
    from_port   = 8001
    to_port     = 8001
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "RAG API"
    from_port   = 8002
    to_port     = 8002
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Get the latest Ubuntu 22.04 LTS AMI
data "aws_ami" "ubuntu" {
  most_recent = true
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
  owners = ["099720109477"] # Canonical
}

# Provision the t3.medium EC2 instance
resource "aws_instance" "app_server" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.micro"
  key_name               = aws_key_pair.fenec_key_pair.key_name
  vpc_security_group_ids = [aws_security_group.fenec_sg.id]

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
  }

  # THIS IS THE BASH SCRIPT AUTOMATION!
  user_data = file("${path.module}/user_data.sh")

  tags = {
    Name = "fenec-ai-callcenter"
  }
}

# Allocate an Elastic IP and attach it to the EC2 instance
resource "aws_eip" "app_eip" {
  instance = aws_instance.app_server.id
  domain   = "vpc"
}

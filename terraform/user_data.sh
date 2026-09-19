#!/bin/bash
# 1. Update the system
apt-get update -y

# 2. CREATE A SWAPFILE (Fake RAM)
# Since the AWS account forces t2.micro (1GB RAM), we need swap space
# so Docker doesn't crash when running EspoCRM and PostgreSQL.
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' | tee -a /etc/fstab

# 3. Install Docker and Docker Compose automatically
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# 4. Give the default ubuntu user permission to run docker without sudo
usermod -aG docker ubuntu

# 5. Make sure Docker starts on reboot
systemctl enable docker
systemctl start docker

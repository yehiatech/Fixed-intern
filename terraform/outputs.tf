output "server_public_ip" {
  description = "The Elastic IP of your new EC2 Server"
  value       = aws_eip.app_eip.public_ip
}

output "ssh_command" {
  description = "Command to SSH into your server"
  value       = "ssh -i ai-callcenter-key.pem ubuntu@${aws_eip.app_eip.public_ip}"
}
